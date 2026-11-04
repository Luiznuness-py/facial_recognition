"""Sessões, tentativas restritas e transições autenticadas da biometria."""
import secrets
from uuid import uuid4, UUID
from datetime import timedelta
from python_multipart.exceptions import MultipartParseError

import numpy as np
from fastapi import (
    HTTPException, Response,
    Request
)

from facial_recognition.core.database import Connection
from facial_recognition.core.settings import settings
from facial_recognition.core.queries import UserQueries
from facial_recognition.utils.utils import now, audit
from facial_recognition.schemas.base_model import ApiResponse
from facial_recognition.core.biometrics import MODEL_VERSION, CAPTURE_FRAMES
from facial_recognition.exceptions.biometrics import BiometricError
from facial_recognition.core.security import (
    encrypt_vector, decrypt_vector, token_hash,
    set_cookie, rotate_csrf,
)


class Authentication:
    """Coordena a identificação da conta e as etapas do fluxo de autenticação.

    Valida sessões e tentativas no banco, emite credenciais, monta respostas públicas e
    conduz o cadastro ou a verificação biométrica. A verificação de permissões pertence
    a Authorization; a assinatura dos JWTs pertence a TokenJwt.

    A instância não guarda usuário, conexão ou tentativa em atributos. Esses dados são
    recebidos pelos métodos em cada chamada, permitindo compartilhar a instância entre
    requisições. Métodos que alteram etapas e sessões usam a transação do chamador;
    process_biometric controla suas transações após a inferência.
    """

    async def issue_stage(self, connection, request, response, attempt, stage):
        """Autoriza a próxima etapa com um novo identificador de JWT restrito.

        Atualiza etapa, jti e expiração no banco, emite o cookie e gira o contexto CSRF. Deve
        ser chamada após validar/bloquear a tentativa, na transação que realiza a transição.

        Args:
            connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
            request: Requisição com cookies e os recursos compartilhados em app.state.
            response: Resposta FastAPI usada para emitir ou expirar cookies.
            attempt: Registro da tentativa restrita, previamente identificado pela dependência.
            stage: Próxima etapa ENROLL_FACE, VERIFY_FACE ou CHANGE_PASSWORD.

        Returns:
            dict: next_step e expires_in=300 para orientar a interface.

        Raises:
            HTTPException: Status 400 se o transporte não permitir emitir o cookie.
        """
        jti = uuid4()
        await connection.execute('UPDATE authentication_attempts SET stage=$2,token_jti=$3,expires_at=$4 WHERE id=$1',
            attempt['id'], stage, jti, now()+timedelta(minutes=5))
        token = request.app.state.tokens.create_token(attempt['user_id'], 'RESTRICTED', 300,
            jti=str(jti), attempt_id=str(attempt['id']), stage=stage, operation=attempt['operation'])
        set_cookie(response, request, 'lab_stage', token, 300)
        rotate_csrf(response, request)
        return dict(next_step=stage, expires_in=300)


    async def issue_session(self, connection, request, response, user):
        """Cria a sessão completa após concluir as etapas exigidas da conta.

        Cria sessão e hash do refresh, emite access de 15 minutos e refresh, remove etapa, gira
        CSRF, limpa contadores biométricos e registra auditoria. O chamador mantém a transação e
        garante que a conta pode receber sessão.

        Args:
            connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
            request: Requisição com cookies e os recursos compartilhados em app.state.
            response: Resposta FastAPI usada para emitir ou expirar cookies.
            user: Conta que já foi autorizada pelo fluxo de login ou ativação.

        Returns:
            dict: Próxima etapa SESSION, prazo de 24 horas e identificação sanitizada.

        Raises:
            HTTPException: Status 400 se o transporte não permitir emitir cookies.
        """
        session = await connection.fetchrow("INSERT INTO sessions(user_id,expires_at) VALUES($1,NOW()+INTERVAL '24 hours') RETURNING *", user['id'])
        refresh = secrets.token_urlsafe(48)
        await connection.execute('INSERT INTO refresh_tokens(session_id,token_hash,expires_at) VALUES($1,$2,$3)', session['id'], token_hash(refresh), session['expires_at'])
        access = request.app.state.tokens.create_token(user['id'], 'ACCESS', 900, session_id=str(session['id']))
        set_cookie(response, request, 'lab_access', access, 900)
        set_cookie(response, request, 'lab_refresh', refresh, 86400)
        response.delete_cookie('lab_stage', path='/api/v1/auth')
        rotate_csrf(response, request)
        await connection.execute('UPDATE users SET biometric_failure_count=0,biometric_failure_window_started_at=NULL,biometric_blocked_until=NULL WHERE id=$1', user['id'])
        await audit(connection, user['id'], 'SESSION_CREATED', 'sessions', session['id'], request_id=request.state.request_id)
        return dict(next_step='SESSION', expires_in=86400, user=await self.build_user_response(connection, user))


    async def lock_attempt(self, connection, attempt):
        """Bloqueia e revalida conta, credencial e tentativa antes de gravar resultados.

        Exige uma transação ativa do chamador. Reconsulta o banco após o processamento para
        impedir que um resultado avance uma etapa invalidada durante a inferência.

        Args:
            connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
            attempt: Registro da tentativa restrita, previamente identificado pela dependência.

        Returns:
            asyncpg.Record: Conta atual com papel, credencial e controles biométricos.

        Raises:
            HTTPException: Status 401 para conta/credencial excluída ou tentativa ausente,
                excluída, consumida, com outro jti ou expirada.
        """
        user = await connection.fetchrow(UserQueries.USER_SQL+'AND u.id=$1 FOR UPDATE OF u,p', attempt['user_id'])
        if not user or user['password_deleted']:
            raise HTTPException(401, 'Conta ou credencial desativada. Entre novamente.')
        current = await connection.fetchrow("SELECT * FROM authentication_attempts WHERE id=$1 FOR UPDATE", attempt['id'])
        if (
            not current
            or current['soft_delete']
            or current['status'] != 'PENDING'
            or current['token_jti'] != attempt['token_jti']
            or current['expires_at'] <= now()
        ):
            raise HTTPException(401, 'Esta etapa já foi utilizada ou expirou.')
        return user


    async def get_current_user(self, request: Request, connection: Connection):
        """Identifica uma conta com access válido e sessão vigente no banco.

        Aceita apenas ACCESS; não aceita JWT de etapa. Confere validade, revogação, exclusão
        lógica, papel e flags da conta a cada requisição.

        Args:
            request: Requisição com cookies e os recursos compartilhados em app.state.
            connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.

        Returns:
            asyncpg.Record: Conta habilitada, ativa e sem etapas obrigatórias pendentes.

        Raises:
            HTTPException: Status 401 para JWT inválido ou sessão/conta/credencial sem acesso
                vigente.
        """
        claims = request.app.state.tokens.validate_token(request.cookies.get('lab_access'), 'ACCESS')
        user = await connection.fetchrow(UserQueries.USER_SQL + """AND u.id=$1 AND u.status='ACTIVE'
            AND NOT u.password_change_required AND NOT u.biometric_enrollment_required
            AND EXISTS(SELECT 1 FROM sessions s WHERE s.id=$2 AND s.user_id=u.id
            AND NOT s.soft_delete AND s.revoked_at IS NULL AND s.expires_at>NOW())""",
            UUID(claims['sub']), UUID(claims['session_id']))
        if not user or user['password_deleted']:
            raise HTTPException(401, 'Sessão encerrada. Entre novamente.')
        return user


    async def get_current_attempt(self, request: Request, connection: Connection):
        """Identifica a tentativa permitida pelo JWT restrito recebido.

        Não renova o prazo nem cria sessão. O resultado ainda deve ser revalidado sob bloqueio
        antes de gravar uma mudança de estado.

        Args:
            request: Requisição com cookies e os recursos compartilhados em app.state.
            connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.

        Returns:
            asyncpg.Record: Tentativa pendente com etapa, operação e jti correspondentes.

        Raises:
            HTTPException: Status 401 para token, tentativa, conta, papel, senha ou bloqueio
                incompatíveis.
        """
        claims = request.app.state.tokens.validate_token(request.cookies.get('lab_stage'), 'RESTRICTED')
        attempt = await connection.fetchrow('''SELECT a.* FROM authentication_attempts a
            JOIN users u ON u.id=a.user_id AND NOT u.soft_delete
            JOIN roles r ON r.id=u.role_id AND NOT r.soft_delete
            JOIN password_hashes p ON p.user_id=u.id AND NOT p.soft_delete
            WHERE a.id=$1 AND a.user_id=$2 AND a.token_jti=$3 AND a.stage=$4 AND a.operation=$5
            AND a.status='PENDING' AND NOT a.soft_delete AND a.expires_at>NOW()
            AND (u.biometric_blocked_until IS NULL OR u.biometric_blocked_until<=NOW())''',
            UUID(claims['attempt_id']), UUID(claims['sub']), UUID(claims['jti']), claims['stage'], claims['operation'])
        if not attempt:
            raise HTTPException(401, 'Etapa encerrada ou expirada. Entre novamente.')
        return attempt


    async def build_user_response(self, connection, user):
        """Seleciona os dados públicos da conta autenticada para a resposta.

        Não inclui hash, flags internas, embeddings ou tokens. A autorização da consulta deve
        ter sido conferida pelo chamador.

        Args:
            connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
            user: Registro da conta com id, name, email, role e team_id.

        Returns:
            dict: Identificação, papel e equipe não excluída, ou team=None.
        """
        team = await connection.fetchrow('SELECT id,code,name,description FROM teams WHERE id=$1 AND NOT soft_delete', user['team_id']) if user['team_id'] else None
        return dict(id=user['id'], name=user['name'], email=user['email'], role=user['role'], team=dict(team) if team else None)



    async def process_biometric(self, request: Request, response: Response, connection: Connection, attempt, enroll: bool):
        """Processa cadastro ou verificação facial e realiza a próxima transição.

        Recebe cinco arquivos JPEG/PNG, encerra o formulário e roda inferência antes da
        transação de gravação. Revalida a tentativa, criptografa o template no cadastro e
        registra auditoria. Apenas reprovação real atualiza contadores; qualidade ruim e falha
        de processamento não contam como fraude.

        Args:
            request: Requisição com cookies e os recursos compartilhados em app.state.
            response: Resposta FastAPI usada para emitir ou expirar cookies.
            connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
            attempt: Registro da tentativa restrita, previamente identificado pela dependência.
            enroll: True para cadastro autorizado; False para verificar o template existente.

        Returns:
            ApiResponse: Próxima etapa de senha ou sessão completa após aprovação.

        Raises:
            HTTPException: 401 para credencial expirada ou reprovação; 403 para etapa errada;
                409 para cadastro ausente/incompatível; 413/422 para upload; 429 para ocupação;
                503 para indisponibilidade.
        """
        if settings.BIOMETRICS_MODE != 'real':
            raise HTTPException(403, 'Use a etapa de simulação neste ambiente.')
        if attempt['stage'] != ('ENROLL_FACE' if enroll else 'VERIFY_FACE'):
            raise HTTPException(403, 'A etapa atual não permite esta operação biométrica.')
        content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
        if content_type != 'multipart/form-data':
            raise HTTPException(422, 'Envie as imagens como multipart/form-data.')
        # O parser mantém as cinco partes em memória, cada uma limitada a 1 MiB.
        from starlette.datastructures import UploadFile
        contents = []
        from starlette.formparsers import MultiPartParser, MultiPartException
        parser = MultiPartParser(request.headers, request.stream(), max_files=CAPTURE_FRAMES, max_fields=0)
        # O corpo já foi limitado a 16 MiB; mesmo arquivos inválidos não vão para disco.
        parser.spool_max_size = 16*1024*1024
        try:
            form = await parser.parse()
        except (MultiPartException, MultipartParseError):
            raise HTTPException(422, 'Envio multipart inválido ou com arquivos em excesso.') from None
        try:
            frames = form.getlist('frames')
            if len(frames) != CAPTURE_FRAMES or any(not isinstance(f, UploadFile) for f in frames) or set(form.keys()) != {'frames'}:
                raise HTTPException(422, f'Envie exatamente {CAPTURE_FRAMES} imagens no campo frames.')
            for image in frames:
                data = await image.read(1024*1024+1)
                if len(data)>1024*1024:
                    raise HTTPException(413, 'Imagem maior que 1 MiB.')
                contents.append(data)
        finally:
            await form.close()
        reference = None
        if not enroll:
            vector = await connection.fetchrow('SELECT * FROM vectors WHERE user_id=$1 AND NOT soft_delete AND model_version=$2 ORDER BY created_at DESC LIMIT 1', attempt['user_id'], MODEL_VERSION)
            if not vector:
                raise HTTPException(409, 'Cadastro facial ausente ou incompatível. Procure o ADMIN.')
            reference = np.frombuffer(decrypt_vector(request.app.state.tokens, attempt['user_id'], vector['ciphertext'], vector['nonce']), dtype=np.float32)
        try:
            template = await request.app.state.inference(contents, reference)
        except BiometricError as error:
            if error.kind == 'rejected':
                async with connection.transaction():
                    user = await self.lock_attempt(connection, attempt)
                    start = user['biometric_failure_window_started_at']
                    reset = not start or now()-start>timedelta(minutes=15) or (user['biometric_blocked_until'] and user['biometric_blocked_until']<=now())
                    failures = 1 if reset else user['biometric_failure_count']+1
                    blocked = now()+timedelta(minutes=5) if failures>=3 else None
                    await connection.execute('UPDATE users SET biometric_failure_count=$2,biometric_failure_window_started_at=$3,biometric_blocked_until=$4 WHERE id=$1', user['id'], failures, now() if reset else start, blocked)
                    await connection.execute("UPDATE authentication_attempts SET biometric_failures=biometric_failures+1,status=CASE WHEN biometric_failures>=2 THEN 'BLOCKED' ELSE status END WHERE id=$1", attempt['id'])
                    if blocked:
                        await connection.execute("UPDATE authentication_attempts SET status='BLOCKED' WHERE user_id=$1 AND status='PENDING'", user['id'])
                    await audit(connection, user['id'], 'BIOMETRIC_REJECTED', 'authentication_attempts', attempt['id'], False, request_id=request.state.request_id)
            status = {'quality':422,'rejected':401,'busy':429,'unavailable':503}.get(error.kind,503)
            raise HTTPException(status, str(error), headers={'Retry-After':'1'} if status==429 else None) from None

        async with connection.transaction():
            user = await self.lock_attempt(connection, attempt)
            if user['is_temporary'] and user['temporary_expires_at']<=now():
                raise HTTPException(401, 'Senha temporária expirada.')
            if enroll:
                if not user['biometric_enrollment_required']:
                    raise HTTPException(409, 'O cadastro facial não está autorizado.')
                encrypted, nonce = encrypt_vector(request.app.state.tokens, user['id'], template.tobytes())
                await connection.execute('UPDATE vectors SET soft_delete=TRUE WHERE user_id=$1 AND NOT soft_delete', user['id'])
                await connection.execute("INSERT INTO vectors(user_id,ciphertext,nonce,key_version,model_version) VALUES($1,$2,$3,'derived-v1',$4)", user['id'], encrypted, nonce, MODEL_VERSION)
                await connection.execute('UPDATE users SET biometric_enrollment_required=FALSE WHERE id=$1', user['id'])
            await audit(connection, user['id'], 'FACE_ENROLLED' if enroll else 'FACE_VERIFIED', 'authentication_attempts', attempt['id'], request_id=request.state.request_id)
            if user['password_change_required']:
                return ApiResponse(data=await self.issue_stage(connection, request, response, attempt, 'CHANGE_PASSWORD'))
            await connection.execute("UPDATE authentication_attempts SET status='COMPLETED',completed_at=NOW() WHERE id=$1", attempt['id'])
            return ApiResponse(data=await self.issue_session(connection, request, response, user))
