"""Rotas de autenticação e funções de apoio do mesmo grupo."""
import secrets
import asyncio
from uuid import uuid4, UUID
from datetime import timedelta

from fastapi import (
    HTTPException, Depends,
    Request, Response, APIRouter,
)

from facial_recognition.utils.utils import now, audit
from facial_recognition.core.settings import settings
from facial_recognition.schemas.base_model import ApiResponse
from facial_recognition.schemas.users import CurrentUserResponse
from facial_recognition.schemas.refresh_tokens import RefreshTokenResponse
from facial_recognition.schemas.password_hashes import PasswordCompleteRequest, PasswordChangeStartRequest
from facial_recognition.core.accounts import revoke_access
from facial_recognition.schemas.authentication_attempts import AuthenticationFlowResponse, AuthenticationStepResponse
from facial_recognition.core import (
    Connection, UserQueries,
    Authentication
)
from facial_recognition.schemas.sessions import (
    LoginResponse, CsrfResponse,
    LoginRequest, SessionResponse, LoginRequiredResponse,
)
from facial_recognition.core.security import (
    token_hash, set_cookie, rotate_csrf, require_csrf,
    csrf_signature, verify_origin, check_password,
    clear_cookies, hash_password, validate_new_password,
)

authentication = Authentication()
router = APIRouter(prefix="/auth", tags=["AUTH"])


async def lock_browser_users(connection, request, user_id=None):
    """Serializa contas do contexto antes de sessões/tentativas, inclusive na troca de conta.

    Exige transação do chamador. Valida os JWTs recebidos, localiza o dono do refresh por hash e
    bloqueia as contas por UUID com FOR NO KEY UPDATE antes de sessões/tentativas.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        user_id: UUID adicional da conta que está entrando, ou None no logout.

    Returns:
        list[tuple[str, dict]]: Tipos e claims válidos dos contextos ACCESS/RESTRICTED; ignora
            JWTs inválidos.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    contexts=[]
    owners={user_id} if user_id else set()
    for name,kind in [('lab_access','ACCESS'),('lab_stage','RESTRICTED')]:
        try:
            claims=request.app.state.tokens.validate_token(request.cookies.get(name),kind)
        except HTTPException:
            continue
        contexts.append((kind,claims))
        owners.add(UUID(claims['sub']))
    if request.cookies.get('lab_refresh'):
        owner=await connection.fetchval('''SELECT s.user_id FROM sessions s JOIN refresh_tokens t ON t.session_id=s.id
            WHERE t.token_hash=$1''',token_hash(request.cookies['lab_refresh']))
        if owner:
            owners.add(owner)
    # As FKs de autoria precisam de KEY SHARE; a identidade não é alterada neste fluxo.
    await connection.fetch('SELECT id FROM users WHERE id=ANY($1::uuid[]) ORDER BY id FOR NO KEY UPDATE',list(owners))
    return contexts


@router.post('/biometric', response_model=ApiResponse[LoginResponse], dependencies=[Depends(require_csrf)], tags=['Auth'])
async def auth_biometric(request: Request, response: Response, connection: Connection, attempt=Depends(authentication.get_current_attempt)):
    """Recebe a verificação facial em POST /auth/biometric.

    CSRF e a tentativa são conferidos pelas dependências. Delega a operação a
    process_biometric com enroll=False.

    Args:
        request: Requisição com cookies e os recursos compartilhados em app.state.
        response: Resposta FastAPI usada para emitir ou expirar cookies.
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        attempt: Registro da tentativa restrita, previamente identificado pela dependência.

    Returns:
        ApiResponse: Transição produzida pelo processamento biométrico compartilhado.

    Raises:
        HTTPException: Propaga as recusas de etapa, credencial, upload ou inferência.
    """
    return await authentication.process_biometric(request, response, connection, attempt, enroll=False)


@router.post('/biometric/enroll', response_model=ApiResponse[LoginResponse], dependencies=[Depends(require_csrf)], tags=['Auth'])
async def auth_biometric_enroll(request: Request, response: Response, connection: Connection, attempt=Depends(authentication.get_current_attempt)):
    """Recebe o cadastro facial autorizado em POST /auth/biometric/enroll.

    CSRF e a tentativa são conferidos pelas dependências. Delega a operação a
    process_biometric com enroll=True.

    Args:
        request: Requisição com cookies e os recursos compartilhados em app.state.
        response: Resposta FastAPI usada para emitir ou expirar cookies.
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        attempt: Registro da tentativa restrita, previamente identificado pela dependência.

    Returns:
        ApiResponse: Transição produzida pelo processamento biométrico compartilhado.

    Raises:
        HTTPException: Propaga as recusas de etapa, credencial, upload ou inferência.
    """
    return await authentication.process_biometric(request, response, connection, attempt, enroll=True)


@router.get('/csrf', response_model=ApiResponse[CsrfResponse], tags=['Auth'])
async def csrf(request: Request, response: Response):
    # GET same-origin fetch pode omitir Origin; cross-site é recusado mesmo assim.
    """Entrega a assinatura CSRF para o contexto do navegador em GET /auth/csrf.

    Cria o contexto aleatório se não houver cookie. A resposta não autentica o usuário e não
    renova sessão ou tentativa.

    Args:
        request: Requisição com cookies e os recursos compartilhados em app.state.
        response: Resposta FastAPI usada para emitir ou expirar cookies.

    Returns:
        ApiResponse[CsrfResponse]: Token de proteção a enviar em X-CSRF-Token.

    Raises:
        HTTPException: Status 403 para chamada cross-site ou Origin diferente; 400 para
            transporte não permitido ao criar cookie.
    """
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Origem não permitida.')
    if request.headers.get('origin'):
        verify_origin(request)
    context = request.cookies.get('lab_csrf_context') or rotate_csrf(response, request)
    return ApiResponse(data={'csrf_token': csrf_signature(request, context)})


@router.get('/flow', response_model=ApiResponse[AuthenticationFlowResponse], tags=['Auth'])
async def flow(attempt=Depends(authentication.get_current_attempt)):
    """Informa a etapa restrita atual para retomar a interface após recarregar.

    GET /auth/flow recebe uma tentativa validada pela dependência. A consulta não prolonga
    seu prazo; a contagem retornada tem mínimo de um segundo.

    Args:
        attempt: Registro da tentativa restrita, previamente identificado pela dependência.

    Returns:
        ApiResponse[AuthenticationFlowResponse]: Etapa, operação e segundos restantes.
    """
    return ApiResponse(data=dict(next_step=attempt['stage'], operation=attempt['operation'], biometrics_mode=settings.BIOMETRICS_MODE, expires_in=max(1,int((attempt['expires_at']-now()).total_seconds()))))


@router.post('/login', response_model=ApiResponse[LoginResponse], dependencies=[Depends(require_csrf)], tags=['Auth'])
async def login(body: LoginRequest, request: Request, response: Response, connection: Connection):
    """Confere email e senha e inicia a autenticação em POST /auth/login.

    Verifica o hash em thread e encerra apenas o contexto anterior deste navegador após
    credenciais corretas. ADMIN troca a temporária sem face; as demais contas cadastram ou
    reconhecem a face antes do acesso completo. A operação usa transação e não redefine a
    senha inicial pelo .env.

    Args:
        body: LoginRequest com email normalizado e senha preservada.
        request: Requisição com cookies e os recursos compartilhados em app.state.
        response: Resposta FastAPI usada para emitir ou expirar cookies.
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.

    Returns:
        ApiResponse[LoginResponse]: Sessão para ADMIN habilitado ou a próxima etapa
            restrita.

    Raises:
        HTTPException: 401 para credenciais inválidas ou temporária vencida; 429 para
            bloqueio biométrico; 400 para transporte de cookies inválido.
    """
    async with connection.transaction():
        user_id = await connection.fetchval('SELECT id FROM users WHERE email=$1',str(body.email))
        contexts = await lock_browser_users(connection,request,user_id)
        user = await connection.fetchrow(UserQueries.USER_SQL+'AND u.id=$1 AND u.email=$2', user_id,str(body.email))
        valid = await asyncio.to_thread(check_password, body.password.get_secret_value(), user['password_hash'] if user else request.app.state.dummy_hash)
        if not user or not valid or user['password_deleted']:
            raise HTTPException(401, 'Email ou senha inválidos.')
        if user['is_temporary'] and user['temporary_expires_at'] <= now():
            raise HTTPException(401, 'Senha temporária expirada. Solicite revalidação ao ADMIN.')
        if user['biometric_blocked_until'] and user['biometric_blocked_until'] > now():
            raise HTTPException(429, 'Reconhecimento bloqueado por cinco minutos. Aguarde.')
        # Login válido troca somente o contexto deste navegador.
        for kind, claims in contexts:
            if kind == 'ACCESS':
                await connection.execute('UPDATE sessions SET revoked_at=NOW() WHERE id=$1', UUID(claims['session_id']))
            else:
                await connection.execute("UPDATE authentication_attempts SET status='CANCELLED' WHERE id=$1 AND status='PENDING'", UUID(claims['attempt_id']))
        if request.cookies.get('lab_refresh'):
            await connection.execute('UPDATE sessions SET revoked_at=NOW() WHERE id IN(SELECT session_id FROM refresh_tokens WHERE token_hash=$1)', token_hash(request.cookies['lab_refresh']))
        clear_cookies(response)
        if user['role'] == 'ADMIN' and not user['password_change_required']:
            return ApiResponse(data=await authentication.issue_session(connection, request, response, user))
        stage = 'CHANGE_PASSWORD' if user['role'] == 'ADMIN' else ('ENROLL_FACE' if user['biometric_enrollment_required'] else 'VERIFY_FACE')
        operation = ('ACTIVATION' if user['status'] == 'PENDING_ACTIVATION' else
                     'RECOVERY' if user['password_change_required'] or user['biometric_enrollment_required'] else 'LOGIN')
        attempt = await connection.fetchrow('''INSERT INTO authentication_attempts(user_id,stage,token_jti,expires_at,operation)
            VALUES($1,$2,$3,$4,$5) RETURNING *''', user['id'], stage, uuid4(), now()+timedelta(minutes=5), operation)
        await audit(connection, user['id'], 'LOGIN_STARTED', 'authentication_attempts', attempt['id'], request_id=request.state.request_id)
        return ApiResponse(data=await authentication.issue_stage(connection, request, response, attempt, stage))


@router.post('/logout', status_code=204, dependencies=[Depends(require_csrf)], tags=['Auth'])
async def logout(request: Request, connection: Connection):
    """Revoga o contexto recebido e limpa os cookies em POST /auth/logout.

    Cancela a tentativa ou revoga a sessão, inclusive quando só resta refresh. Registra
    LOGOUT com a autoria identificada na mesma transação; uma chamada anônima só limpa os
    cookies. Não encerra sessões de outros navegadores por usuário.

    Args:
        request: Requisição com cookies e os recursos compartilhados em app.state.
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.

    Returns:
        Response: Status 204 sem corpo, com instruções para expirar os cookies.
    """
    actor = None
    target = None
    resource_type = 'sessions'
    async with connection.transaction():
        contexts = await lock_browser_users(connection,request)
        for kind, claims in contexts:
            actor = UUID(claims['sub'])
            if kind=='ACCESS':
                target = UUID(claims['session_id'])
                resource_type = 'sessions'
                await connection.execute('UPDATE sessions SET revoked_at=NOW() WHERE id=$1', target)
            else:
                target = UUID(claims['attempt_id'])
                resource_type = 'authentication_attempts'
                await connection.execute("UPDATE authentication_attempts SET status='CANCELLED' WHERE id=$1 AND status='PENDING'", target)
        if request.cookies.get('lab_refresh'):
            session = await connection.fetchrow('''UPDATE sessions SET revoked_at=NOW()
                WHERE id IN(SELECT session_id FROM refresh_tokens WHERE token_hash=$1)
                RETURNING id,user_id''', token_hash(request.cookies['lab_refresh']))
            if session:
                actor = session['user_id']
                target = session['id']
                resource_type = 'sessions'
        if actor is not None:
            await audit(connection, actor, 'LOGOUT', resource_type, target, request_id=request.state.request_id)
    response = Response(status_code=204)
    clear_cookies(response)
    return response


@router.get('/me', response_model=ApiResponse[CurrentUserResponse], tags=['Auth'])
async def me(connection: Connection, user=Depends(authentication.get_current_user)):
    """Apresenta a conta e as permissões atuais em GET /auth/me.

    A lista orienta a interface, mas não substitui a verificação de permissão nas demais
    rotas.

    Args:
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        user: Conta autenticada por get_current_user.

    Returns:
        ApiResponse[CurrentUserResponse]: Identificação sanitizada, equipe e códigos de
            permissões vigentes.
    """
    data = await authentication.build_user_response(connection, user)
    permissions = await connection.fetch('''SELECT p.code FROM permissions p JOIN role_permissions rp ON rp.permission_id=p.id
        WHERE rp.role_id=$1 AND NOT rp.soft_delete AND NOT p.soft_delete ORDER BY p.code''', user['role_id'])
    data['permissions'] = [row['code'] for row in permissions]
    return ApiResponse(data=data)


@router.post('/password/complete', response_model=ApiResponse[SessionResponse], dependencies=[Depends(require_csrf)], tags=['Auth'])
async def complete(body: PasswordCompleteRequest, request: Request, response: Response, connection: Connection, attempt=Depends(authentication.get_current_attempt)):
    """Conclui a definição de senha em POST /auth/password/complete.

    Gera e compara hashes em thread, revalida sob bloqueio e atualiza na transação. Preserva
    activated_at, invalida a temporária, cancela outras tentativas pendentes e emite sessão.
    Troca voluntária usa o contrato separado /password-change/complete.

    Args:
        body: Nova senha e confirmação validadas pelo schema.
        request: Requisição com cookies e os recursos compartilhados em app.state.
        response: Resposta FastAPI usada para emitir ou expirar cookies.
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        attempt: Registro da tentativa restrita, previamente identificado pela dependência.

    Returns:
        ApiResponse[SessionResponse]: Sessão completa após ativação ou recuperação.

    Raises:
        HTTPException: 403 para etapa/operação errada ou face pendente; 401 para
            credencial/tentativa inválida ou vencida; 422 para senha fraca ou igual à
            temporária.
    """
    if attempt['stage'] != 'CHANGE_PASSWORD' or attempt['operation'] not in {'ACTIVATION', 'RECOVERY'}:
        raise HTTPException(403, 'A etapa atual não permite definir senha.')
    password = body.new_password.get_secret_value()
    validate_new_password(password)
    encoded = await asyncio.to_thread(hash_password, password)
    async with connection.transaction():
        user = await authentication.lock_attempt(connection, attempt)
        if user['biometric_enrollment_required']:
            raise HTTPException(403, 'Conclua o cadastro facial antes de definir a senha.')
        if user['is_temporary'] and user['temporary_expires_at']<=now():
            raise HTTPException(401, 'Senha temporária expirada.')
        if await asyncio.to_thread(check_password, password, user['password_hash']):
            raise HTTPException(422, 'Escolha uma senha diferente da temporária.')
        await connection.execute('UPDATE password_hashes SET password_hash=$2,is_temporary=FALSE,temporary_expires_at=NULL,updated_at=NOW(),updated_by=$1 WHERE user_id=$1', user['id'], encoded)
        await connection.execute("UPDATE users SET status='ACTIVE',activated_at=COALESCE(activated_at,NOW()),password_change_required=FALSE,updated_at=NOW(),updated_by=$1 WHERE id=$1", user['id'])
        await connection.execute("UPDATE authentication_attempts SET status='COMPLETED',completed_at=NOW() WHERE id=$1", attempt['id'])
        await connection.execute("UPDATE authentication_attempts SET status='CANCELLED' WHERE user_id=$1 AND status='PENDING'", user['id'])
        user = await connection.fetchrow(UserQueries.USER_SQL+'AND u.id=$1', user['id'])
        return ApiResponse(data=await authentication.issue_session(connection, request, response, user))


@router.post('/refresh', response_model=ApiResponse[RefreshTokenResponse], dependencies=[Depends(require_csrf)], tags=['Auth'])
async def refresh(request: Request, response: Response, connection: Connection):
    """Renova access e gira o refresh em POST /auth/refresh.

    Localiza o token e bloqueia sessão antes do refresh, revalidando ambos. O sucessor mantém o prazo final original de até
    24 horas. Reutilização revoga a sessão e essa revogação é confirmada antes de responder
    401. O token original só é localizado por seu hash.

    Args:
        request: Requisição com cookies e os recursos compartilhados em app.state.
        response: Resposta FastAPI usada para emitir ou expirar cookies.
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.

    Returns:
        ApiResponse[RefreshTokenResponse]: Prazo em segundos do novo access.

    Raises:
        HTTPException: Status 401 para refresh desconhecido, reutilizado ou sessão/conta
            inválida; 400 para transporte de cookies não permitido.
    """
    invalid = False
    async with connection.transaction():
        token = await connection.fetchrow('SELECT * FROM refresh_tokens WHERE token_hash=$1', token_hash(request.cookies.get('lab_refresh','')))
        if not token:
            raise HTTPException(401, 'Renovação inválida.')
        session = await connection.fetchrow('SELECT * FROM sessions WHERE id=$1 FOR UPDATE', token['session_id'])
        if not session:
            raise HTTPException(401, 'Renovação inválida.')
        # Revogação também bloqueia sessão antes de refresh; a leitura inicial não autoriza rotação.
        token = await connection.fetchrow('SELECT * FROM refresh_tokens WHERE id=$1 AND session_id=$2 FOR UPDATE', token['id'], session['id'])
        if not token:
            raise HTTPException(401, 'Renovação inválida.')
        user = await connection.fetchrow(UserQueries.USER_SQL+'AND u.id=$1', session['user_id'])
        invalid = token['used_at'] or token['revoked_at'] or token['soft_delete'] or token['expires_at']<=now() or session['revoked_at'] or session['soft_delete'] or session['expires_at']<=now() or not user or user['password_deleted'] or user['status']!='ACTIVE' or user['password_change_required'] or user['biometric_enrollment_required']
        if invalid:
            await connection.execute('UPDATE sessions SET revoked_at=NOW() WHERE id=$1', session['id'])
        else:
            remaining = max(1,int((session['expires_at']-now()).total_seconds()))
            fresh = secrets.token_urlsafe(48)
            successor = await connection.fetchval('INSERT INTO refresh_tokens(session_id,token_hash,expires_at) VALUES($1,$2,$3) RETURNING id', session['id'],token_hash(fresh),session['expires_at'])
            await connection.execute('UPDATE refresh_tokens SET used_at=NOW(),replaced_by_id=$2 WHERE id=$1', token['id'], successor)
            ttl = min(900,remaining)
            access = request.app.state.tokens.create_token(user['id'],'ACCESS',ttl,session_id=str(session['id']))
            set_cookie(response,request,'lab_access',access,ttl)
            set_cookie(response,request,'lab_refresh',fresh,remaining)
            rotate_csrf(response,request)
    if invalid:
        raise HTTPException(401, 'Renovação reutilizada ou sessão encerrada. Entre novamente.')
    return ApiResponse(data={'expires_in':ttl})


@router.post('/biometric/simulate', response_model=ApiResponse[LoginResponse], dependencies=[Depends(require_csrf)], tags=['Auth'])
async def simulate_biometric(request: Request, response: Response, connection: Connection,
                             attempt=Depends(authentication.get_current_attempt)):
    """Avança a etapa facial sem câmera somente no modo de simulação local.

    Aceita apenas development/test no modo simulated e corpo vazio. Revalida conta/tentativa sob
    lock, registra BIOMETRIC_SIMULATED e avança sem inferência ou vetores fictícios.

    Args:
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        response: Resposta FastAPI que recebe emissão ou limpeza dos cookies de autenticação.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        attempt: Tentativa restrita identificada pela dependência e revalidada sob lock antes da
            escrita.

    Returns:
        ApiResponse[LoginResponse]: Próxima etapa de senha ou sessão completa.

    Raises:
        HTTPException: Status 403 para modo/operação/etapa proibidos; 422 para corpo; 401 para
            credencial expirada/inválida; 409 para cadastro não autorizado.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    if settings.BIOMETRICS_MODE != 'simulated' or settings.ENVIRONMENT not in {'development', 'test'}:
        raise HTTPException(403, 'Simulação biométrica não está habilitada.')
    if attempt['stage'] not in {'ENROLL_FACE', 'VERIFY_FACE'} or attempt['operation'] not in {'ACTIVATION', 'LOGIN', 'RECOVERY', 'PASSWORD_CHANGE'}:
        raise HTTPException(403, 'A etapa atual não permite esta operação.')
    if await request.body():
        raise HTTPException(422, 'A simulação não recebe campos ou imagens.')
    async with connection.transaction():
        user = await authentication.lock_attempt(connection, attempt)
        if user['is_temporary'] and user['temporary_expires_at'] <= now():
            raise HTTPException(401, 'Senha temporária expirada.')
        if attempt['stage'] == 'ENROLL_FACE':
            if not user['biometric_enrollment_required']:
                raise HTTPException(409, 'O cadastro facial não está autorizado.')
            await connection.execute('UPDATE users SET biometric_enrollment_required=FALSE WHERE id=$1', user['id'])
        await audit(connection, user['id'], 'BIOMETRIC_SIMULATED', 'authentication_attempts',
                    attempt['id'], request_id=request.state.request_id)
        if user['password_change_required'] or attempt['operation'] == 'PASSWORD_CHANGE':
            return ApiResponse(data=await authentication.issue_stage(connection, request, response, attempt, 'CHANGE_PASSWORD'))
        await connection.execute("UPDATE authentication_attempts SET status='COMPLETED',completed_at=NOW() WHERE id=$1", attempt['id'])
        return ApiResponse(data=await authentication.issue_session(connection, request, response, user))


@router.post('/password-change/start', response_model=ApiResponse[AuthenticationStepResponse], dependencies=[Depends(require_csrf)])
async def password_change_start(body: PasswordChangeStartRequest, request: Request, response: Response, connection: Connection, current=Depends(authentication.get_current_user)):
    """Confirma a senha e vincula a troca à sessão iniciadora sem encerrá-la.

    Bloqueia conta e credencial, compara a senha em thread e revalida a sessão. Cancela outra
    troca pendente da mesma sessão e cria prova PASSWORD_CHANGE sem encerrar o acesso atual.

    Args:
        body: PasswordChangeStartRequest validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        response: Resposta FastAPI que recebe emissão ou limpeza dos cookies de autenticação.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        current: Conta autenticada cuja sessão inicia a troca voluntária.

    Returns:
        ApiResponse[AuthenticationStepResponse]: Etapa VERIFY_FACE ou CHANGE_PASSWORD para
            ADMIN.

    Raises:
        HTTPException: Status 401 para senha inválida, credencial temporária ou sessão
            encerrada.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    claims = request.app.state.tokens.validate_token(request.cookies.get('lab_access'), 'ACCESS')
    session_id = UUID(claims['session_id'])
    async with connection.transaction():
        user = await connection.fetchrow(UserQueries.USER_SQL+' AND u.id=$1 FOR UPDATE OF u,p', current['id'])
        if not user or user['password_deleted'] or user['is_temporary'] or not await asyncio.to_thread(check_password, body.current_password.get_secret_value(), user['password_hash']):
            raise HTTPException(401, 'Senha atual inválida.')
        if not await connection.fetchval('SELECT EXISTS(SELECT 1 FROM sessions WHERE id=$1 AND user_id=$2 AND revoked_at IS NULL AND NOT soft_delete AND expires_at>NOW())', session_id, user['id']):
            raise HTTPException(401, 'Sessão encerrada.')
        await connection.execute("UPDATE authentication_attempts SET status='CANCELLED' WHERE initiating_session_id=$1 AND status='PENDING'", session_id)
        stage = 'CHANGE_PASSWORD' if user['role'] == 'ADMIN' else 'VERIFY_FACE'
        attempt = await connection.fetchrow('''INSERT INTO authentication_attempts(user_id,stage,token_jti,expires_at,operation,initiating_session_id)
            VALUES($1,$2,$3,$4,'PASSWORD_CHANGE',$5) RETURNING *''', user['id'], stage, uuid4(), now()+timedelta(minutes=5), session_id)
        await audit(connection, user['id'], 'PASSWORD_CHANGE_STARTED', 'authentication_attempts', attempt['id'], request_id=request.state.request_id)
        return ApiResponse(data=await authentication.issue_stage(connection, request, response, attempt, stage))


@router.post('/password-change/complete', response_model=ApiResponse[LoginRequiredResponse], dependencies=[Depends(require_csrf)])
async def password_change_complete(body: PasswordCompleteRequest, request: Request, response: Response, connection: Connection, attempt=Depends(authentication.get_current_attempt)):
    """Atualiza a senha após a prova exigida e encerra todas as sessões atomicamente.

    Exige ACCESS da sessão iniciadora e etapa PASSWORD_CHANGE/CHANGE_PASSWORD. Calcula e compara
    hashes em thread, revalida sob lock e altera senha, revoga acessos e audita atomicamente.

    Args:
        body: PasswordCompleteRequest validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        response: Resposta FastAPI que recebe emissão ou limpeza dos cookies de autenticação.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        attempt: Tentativa restrita identificada pela dependência e revalidada sob lock antes da
            escrita.

    Returns:
        ApiResponse[LoginRequiredResponse]: Próxima etapa LOGIN e limpeza dos cookies.

    Raises:
        HTTPException: Status 403 para operação/etapa incompatíveis; 401 para sessão/tentativa
            inválida; 422 para senha fraca ou igual à atual.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    if attempt['operation'] != 'PASSWORD_CHANGE' or attempt['stage'] != 'CHANGE_PASSWORD':
        raise HTTPException(403, 'Etapa incompatível com a troca de senha.')
    claims = request.app.state.tokens.validate_token(request.cookies.get('lab_access'), 'ACCESS')
    if UUID(claims['session_id']) != attempt['initiating_session_id']:
        raise HTTPException(401, 'Use a sessão que iniciou a troca.')
    password = body.new_password.get_secret_value()
    validate_new_password(password)
    encoded = await asyncio.to_thread(hash_password, password)
    async with connection.transaction():
        user = await authentication.lock_attempt(connection, attempt)
        if not await connection.fetchval('SELECT EXISTS(SELECT 1 FROM sessions WHERE id=$1 AND user_id=$2 AND revoked_at IS NULL AND NOT soft_delete AND expires_at>NOW())', attempt['initiating_session_id'], user['id']):
            raise HTTPException(401, 'Sessão iniciadora encerrada.')
        if await asyncio.to_thread(check_password, password, user['password_hash']):
            raise HTTPException(422, 'Escolha uma senha diferente da atual.')
        await connection.execute('UPDATE password_hashes SET password_hash=$2,updated_at=NOW(),updated_by=$1 WHERE user_id=$1', user['id'], encoded)
        await connection.execute("UPDATE authentication_attempts SET status='COMPLETED',completed_at=NOW() WHERE id=$1", attempt['id'])
        await revoke_access(connection, user['id'])
        await audit(connection, user['id'], 'PASSWORD_CHANGED', 'users', user['id'], request_id=request.state.request_id)
        clear_cookies(response)
        return ApiResponse(data={'next_step':'LOGIN'})
