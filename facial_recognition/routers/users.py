"""Endpoint users."""
from typing import Annotated
from uuid import UUID
from datetime import timedelta

import asyncpg

from fastapi import Depends, Query, APIRouter, Request, HTTPException
from facial_recognition.core.accounts import check_position, password_hash, revoke_access, set_temporary_password
from facial_recognition.core.security import require_csrf
from facial_recognition.utils.utils import now, audit

from facial_recognition.core import Connection, Authorization
from facial_recognition.schemas.users import (
    UserResponse, UserQuery, UserUpdate, UserDeactivate, UserReactivate, UserRecovery, UserActivationResponse,
)
from facial_recognition.schemas.base_model import ApiResponse, ListResponse


router = APIRouter(prefix="/users", tags=["USERS"])


@router.get('/', response_model=ApiResponse[ListResponse[UserResponse]], tags=['Accounts'])
async def users(connection: Connection, query: Annotated[UserQuery, Query()], admin=Depends(Authorization('accounts.manage'))):
    """Lista contas administrativas com filtros e paginação em GET /users.

    Ordena pela criação mais recente. Hashes, embeddings e controles biométricos não entram
    no schema de resposta.

    Args:
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        query: Página, tamanho, pesquisa, status e filtro de exclusão lógica.
        admin: Conta autenticada com accounts.manage.

    Returns:
        ApiResponse[ListResponse[UserResponse]]: Itens sanitizados e total com os mesmos
            filtros.
    """
    where = '''FROM users u JOIN roles r ON r.id=u.role_id AND NOT r.soft_delete WHERE u.soft_delete=$1
        AND ($2::text IS NULL OR u.name ILIKE '%'||$2||'%' OR u.email ILIKE '%'||$2||'%')
        AND ($3::text IS NULL OR u.status=$3)'''
    rows = await connection.fetch('SELECT u.*,r.code AS role_code '+where+' ORDER BY u.created_at DESC LIMIT $4 OFFSET $5',query.soft_delete,query.search,query.status,query.per_page,(query.page-1)*query.per_page)
    total = await connection.fetchval('SELECT count(*) '+where,query.soft_delete,query.search,query.status)
    return ApiResponse(data={'items':[UserResponse.model_validate(dict(row),extra='ignore') for row in rows],'total':total})


async def account_row(connection, id, lock=False):
    """Obtém inclusive contas desativadas para ações administrativas autorizadas.

    O chamador exige accounts.manage. Inclui contas desativadas para consulta/restauração
    administrativa; lock=True exige transação.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        id: UUID da conta, inclusive desativada.
        lock: Se True, mantém FOR UPDATE OF u até o término da transação.

    Returns:
        asyncpg.Record: Conta institucional e código do papel vigente.

    Raises:
        HTTPException: Status 404 para conta ausente ou papel excluído.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row = await connection.fetchrow('''SELECT u.*,r.code AS role_code FROM users u
        JOIN roles r ON r.id=u.role_id AND NOT r.soft_delete WHERE u.id=$1'''+(' FOR UPDATE OF u' if lock else ''), id)
    if not row:
        raise HTTPException(404, 'Conta não encontrada.')
    return row


@router.get('/{id}', response_model=ApiResponse[UserResponse])
async def user_detail(id: UUID, connection: Connection, admin=Depends(Authorization('accounts.manage'))):
    """Consulta os dados administrativos sem credenciais ou vetores.

    Exige accounts.manage e seleciona o schema administrativo. Inclui conta desativada sem expor
    senha, vetores ou conteúdo científico.

    Args:
        id: UUID da conta.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        admin: Conta autenticada com a permissão administrativa accounts.manage.

    Returns:
        ApiResponse[UserResponse]: Dados institucionais, estado e flags da conta.

    Raises:
        HTTPException: Status 404 para conta ausente ou papel excluído.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    return ApiResponse(data=UserResponse.model_validate(dict(await account_row(connection, id)), extra='ignore'))


@router.patch('/{id}', response_model=ApiResponse[UserResponse], dependencies=[Depends(require_csrf)])
async def update_user(id: UUID, body: UserUpdate, request: Request, connection: Connection, admin=Depends(Authorization('accounts.manage'))):
    """Corrige a conta e revoga acesso quando email, papel ou equipe mudam.

    Serializa cadastros e bloqueia a conta. Confere identidade, papel/equipe e vaga; mudança de
    email/papel/equipe revoga acesso. Auditoria e atualização são atômicas.

    Args:
        id: UUID da conta a corrigir.
        body: UserUpdate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        admin: Conta autenticada com a permissão administrativa accounts.manage.

    Returns:
        ApiResponse[UserResponse]: Conta após as alterações institucionais permitidas.

    Raises:
        HTTPException: Status 404 para conta ausente; 403 para alteração de ADMIN; 422 para
            papel/equipe inválidos; 409 para conta desativada, conflito de identidade/vaga ou
            responsável ainda em preparação.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    try:
        async with connection.transaction():
            await connection.execute('SELECT pg_advisory_xact_lock(827462)')
            row = await account_row(connection, id, True)
            if row['soft_delete']:
                raise HTTPException(409, 'Reative a conta antes de alterá-la.')
            values = body.model_dump(exclude_unset=True)
            role_code = values.get('role_code', row['role_code'])
            if row['role_code'] == 'ADMIN' or role_code == 'ADMIN':
                raise HTTPException(403, 'O administrador institucional não pode ser alterado por este fluxo.')
            if role_code == 'N3' and 'team_id' in values:
                raise HTTPException(422, 'N3 não possui equipe.')
            team = values.get('team_id', row['team_id']) if role_code in {'N1','N2'} else None
            if (role_code, team) != (row['role_code'], row['team_id']) and await connection.fetchval('''SELECT EXISTS(
                SELECT 1 FROM validations WHERE responsible_user_id=$1 AND NOT soft_delete AND status IN ('OPEN','RETURNED'))''', id):
                raise HTTPException(409, 'Substitua o responsável das investigações em preparação antes de mudar papel ou equipe.')
            role = await check_position(connection, role_code, team, id)
            name, email = values.get('name', row['name']), str(values.get('email', row['email']))
            if email != row['email'] and await connection.fetchval('''SELECT EXISTS(SELECT 1 FROM access_requests
                WHERE requested_email=$1 AND status='PENDING' AND NOT soft_delete)''', email):
                raise HTTPException(409, 'Email reservado por uma solicitação pendente.')
            await connection.execute('''UPDATE users SET name=$2,email=$3,role_id=$4,team_id=$5,
                updated_at=NOW(),updated_by=$6 WHERE id=$1''', id, name, email, role, team, admin['id'])
            if (email, role, team) != (row['email'], row['role_id'], row['team_id']):
                await revoke_access(connection, id)
            await audit(connection, admin['id'], 'USER_UPDATED', 'users', id, request_id=request.state.request_id)
            return ApiResponse(data=UserResponse.model_validate(dict(await account_row(connection, id)), extra='ignore'))
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, 'Email já cadastrado.') from None


@router.post('/{id}/deactivate', response_model=ApiResponse[UserResponse], dependencies=[Depends(require_csrf)])
async def deactivate(id: UUID, body: UserDeactivate, request: Request, connection: Connection, admin=Depends(Authorization('accounts.manage'))):
    """Bloqueia a conta imediatamente e preserva sua identidade e histórico.

    Bloqueia a conta, marca soft_delete e revoga sessões/refresh/tentativas com auditoria.
    Preserva status, identidade, primeira ativação e histórico científico.

    Args:
        id: UUID da conta institucional a desativar.
        body: UserDeactivate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        admin: Conta autenticada com a permissão administrativa accounts.manage.

    Returns:
        ApiResponse[UserResponse]: Conta desativada com dados históricos preservados.

    Raises:
        HTTPException: Status 404 para conta ausente; 403 para ADMIN; 409 para conta já
            desativada.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        await connection.execute('SELECT pg_advisory_xact_lock(827462)')
        row = await account_row(connection, id, True)
        if row['role_code'] == 'ADMIN':
            raise HTTPException(403, 'Não é permitido desativar o administrador institucional.')
        if row['soft_delete']:
            raise HTTPException(409, 'Conta já desativada.')
        await connection.execute('UPDATE users SET soft_delete=TRUE,updated_at=NOW(),updated_by=$2 WHERE id=$1', id, admin['id'])
        await revoke_access(connection, id)
        await audit(connection, admin['id'], 'USER_DEACTIVATED', 'users', id, reason=body.reason, request_id=request.state.request_id)
        return ApiResponse(data=UserResponse.model_validate(dict(await account_row(connection, id)), extra='ignore'))


@router.post('/{id}/reactivate', response_model=ApiResponse[UserActivationResponse], dependencies=[Depends(require_csrf)])
async def reactivate(id: UUID, body: UserReactivate, request: Request, connection: Connection, admin=Depends(Authorization('accounts.manage'))):
    """Restaura a conta com credenciais novas sem alterar sua primeira ativação.

    Calcula a nova temporária em thread e revalida conta/vaga sob lock. Restaura
    PENDING_ACTIVATION, exige senha/face aplicáveis, revoga acessos e preserva activated_at.

    Args:
        id: UUID da conta desativada a restaurar.
        body: UserReactivate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        admin: Conta autenticada com a permissão administrativa accounts.manage.

    Returns:
        ApiResponse[UserActivationResponse]: Mesma conta restaurada e validade da temporária.

    Raises:
        HTTPException: Status 404 para conta ausente; 409 para conta vigente ou vaga ocupada;
            422 para senha/papel/equipe inválidos.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    encoded = await password_hash(body.temporary_password)
    async with connection.transaction():
        await connection.execute('SELECT pg_advisory_xact_lock(827462)')
        row = await account_row(connection, id, True)
        if not row['soft_delete']:
            raise HTTPException(409, 'A conta não está desativada.')
        await check_position(connection, row['role_code'], row['team_id'], id)
        await revoke_access(connection, id)
        await connection.execute('UPDATE vectors SET soft_delete=TRUE WHERE user_id=$1', id)
        expires = await set_temporary_password(connection, id, encoded, admin['id'])
        await connection.execute('''UPDATE users SET soft_delete=FALSE,status='PENDING_ACTIVATION',
            password_change_required=TRUE,biometric_enrollment_required=$2,biometric_failure_count=0,
            biometric_failure_window_started_at=NULL,biometric_blocked_until=NULL,updated_at=NOW(),updated_by=$3 WHERE id=$1''', id, row['role_code'] != 'ADMIN', admin['id'])
        await audit(connection, admin['id'], 'USER_REACTIVATED', 'users', id, reason=body.reason, request_id=request.state.request_id)
        return ApiResponse(data=UserActivationResponse.model_validate(dict(await account_row(connection, id), temporary_expires_at=expires), extra='ignore'))


@router.post('/{id}/activation/revalidate', response_model=ApiResponse[UserActivationResponse], dependencies=[Depends(require_csrf)])
async def revalidate(id: UUID, request: Request, connection: Connection, admin=Depends(Authorization('accounts.manage'))):
    """Renova a validade da mesma temporária, preservando o cadastro facial concluído.

    Bloqueia conta e credencial temporária pendente. Renova 24 horas sem trocar hash ou face e
    revoga acessos anteriores na mesma transação da auditoria.

    Args:
        id: UUID da conta com ativação temporária pendente.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        admin: Conta autenticada com a permissão administrativa accounts.manage.

    Returns:
        ApiResponse[UserActivationResponse]: Conta pendente e nova expiração da mesma
            temporária.

    Raises:
        HTTPException: Status 404 para conta ausente; 409 para conta/credencial sem ativação
            temporária pendente.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await account_row(connection, id, True)
        password = await connection.fetchrow('SELECT * FROM password_hashes WHERE user_id=$1 AND NOT soft_delete FOR UPDATE', id)
        if row['soft_delete'] or row['status'] != 'PENDING_ACTIVATION' or not password or not password['is_temporary']:
            raise HTTPException(409, 'A conta não possui ativação temporária pendente.')
        expires = now() + timedelta(hours=24)
        await connection.execute('UPDATE password_hashes SET temporary_expires_at=$2,updated_at=NOW(),updated_by=$3 WHERE user_id=$1', id, expires, admin['id'])
        await revoke_access(connection, id)
        await audit(connection, admin['id'], 'ACTIVATION_REVALIDATED', 'users', id, request_id=request.state.request_id)
        return ApiResponse(data=UserActivationResponse.model_validate(dict(row, temporary_expires_at=expires), extra='ignore'))


@router.post('/{id}/recovery', response_model=ApiResponse[UserActivationResponse], dependencies=[Depends(require_csrf)])
async def recovery(id: UUID, body: UserRecovery, request: Request, connection: Connection, admin=Depends(Authorization('accounts.manage'))):
    """Autoriza recuperação de senha, face ou ambas e invalida os acessos anteriores.

    Exige conta institucional ACTIVE não excluída e autorização ADMIN. Conforme
    PASSWORD/BIOMETRIC/BOTH, redefine temporária e/ou exclui vetores, revogando acessos e
    preservando primeira ativação.

    Args:
        id: UUID da conta institucional em recuperação.
        body: UserRecovery validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        admin: Conta autenticada com a permissão administrativa accounts.manage.

    Returns:
        ApiResponse[UserActivationResponse]: Conta com exigências de recuperação e expiração
            quando houver temporária.

    Raises:
        HTTPException: Status 404 para conta ausente; 403 para ADMIN como alvo; 409 para conta
            não ativa; 422 para temporária inválida.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    encoded = await password_hash(body.temporary_password) if body.temporary_password else None
    async with connection.transaction():
        row = await account_row(connection, id, True)
        if row['role_code'] == 'ADMIN':
            raise HTTPException(403, 'Recuperação da conta ADMIN está fora deste fluxo.')
        if row['soft_delete'] or row['status'] != 'ACTIVE':
            raise HTTPException(409, 'Recuperação exige conta ativa.')
        face = body.mode in {'BIOMETRIC','BOTH'}
        await revoke_access(connection, id)
        expires = None
        if encoded:
            expires = await set_temporary_password(connection, id, encoded, admin['id'])
        if face:
            await connection.execute('UPDATE vectors SET soft_delete=TRUE WHERE user_id=$1', id)
        await connection.execute('''UPDATE users SET password_change_required=password_change_required OR $2,
            biometric_enrollment_required=biometric_enrollment_required OR $3,biometric_failure_count=0,
            biometric_failure_window_started_at=NULL,biometric_blocked_until=NULL,updated_at=NOW(),updated_by=$4 WHERE id=$1''', id, encoded is not None, face, admin['id'])
        await audit(connection, admin['id'], 'USER_RECOVERY_AUTHORIZED', 'users', id, reason=body.reason, request_id=request.state.request_id)
        return ApiResponse(data=UserActivationResponse.model_validate(dict(await account_row(connection, id), temporary_expires_at=expires), extra='ignore'))
