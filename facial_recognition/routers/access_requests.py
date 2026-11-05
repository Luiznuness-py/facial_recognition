"""Solicitações institucionais e decisões administrativas de acesso."""
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from facial_recognition.core import Connection, Authorization
from facial_recognition.core.accounts import check_position, password_hash, set_temporary_password
from facial_recognition.schemas.access_requests import AccessRequestCreate, AccessRequestResponse, AccessRequestQuery, AccessRequestReject
from facial_recognition.schemas.base_model import ApiResponse, ListResponse
from facial_recognition.core.security import require_csrf
from facial_recognition.utils.utils import audit

router = APIRouter(prefix='/access-requests', tags=['Accounts'])


async def approve_request(connection, row, actor):
    """Cria a conta e consome o hash do pedido na mesma transação do chamador.

    Exige pedido PENDING bloqueado e transação do chamador. Confere papel/vaga, cria a conta e a
    temporária e remove o hash do pedido ao aprová-lo.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        row: Pedido pendente previamente bloqueado e autorizado.
        actor: UUID da conta que executa a operação e será registrada na autoria.

    Returns:
        asyncpg.Record: Pedido aprovado com user_id e autoria da decisão.

    Raises:
        HTTPException: Status 422 para papel/equipe inválidos; 409 para vaga ocupada.
        asyncpg.UniqueViolationError: Quando a identidade já existe no banco.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    role_code = await connection.fetchval('SELECT code FROM roles WHERE id=$1 AND NOT soft_delete', row['requested_role_id'])
    await check_position(connection, role_code, row['requested_team_id'])
    user_id = await connection.fetchval('''INSERT INTO users(name,email,role_id,team_id,created_by)
        VALUES($1,$2,$3,$4,$5) RETURNING id''', row['requested_name'], row['requested_email'], row['requested_role_id'], row['requested_team_id'], actor)
    await set_temporary_password(connection, user_id, row['temporary_password_hash'], actor)
    return await connection.fetchrow('''UPDATE access_requests SET user_id=$2,status='APPROVED',temporary_password_hash=NULL,
        decided_by=$3,decided_at=NOW(),updated_at=NOW(),updated_by=$3 WHERE id=$1 RETURNING *''', row['id'], user_id, actor)


@router.post('', response_model=ApiResponse[AccessRequestResponse], status_code=201, dependencies=[Depends(require_csrf)])
async def create_account(body: AccessRequestCreate, request: Request, connection: Connection, user=Depends(Authorization('accounts.request'))):
    """Deriva o escopo do solicitante e aprova diretamente somente para ADMIN.

    Deriva N1/equipe para N2 e restringe N3 a pedidos N2. Calcula o hash fora do loop e grava
    pedido, eventual aprovação ADMIN e auditoria na mesma transação.

    Args:
        body: AccessRequestCreate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[AccessRequestResponse]: Pedido criado; inclui user_id somente se aprovado.

    Raises:
        HTTPException: Status 403 para escopo indevido; 422 para dados/política inválidos; 409
            para identidade ou vaga ocupada.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    role_code = await connection.fetchval('SELECT code FROM roles WHERE id=$1 AND NOT soft_delete', user['role_id'])
    target, team = body.role_code, body.team_id
    if role_code == 'N2':
        if target not in {None, 'N1'} or team not in {None, user['team_id']}:
            raise HTTPException(403, 'Solicite N1 somente para sua equipe.')
        target, team = 'N1', user['team_id']
    elif role_code == 'N3':
        if target not in {None, 'N2'}:
            raise HTTPException(403, 'N3 solicita somente contas N2.')
        target = 'N2'
    encoded = await password_hash(body.temporary_password)
    try:
        async with connection.transaction():
            role = await check_position(connection, target, team)
            if await connection.fetchval('SELECT EXISTS(SELECT 1 FROM users WHERE email=$1)', str(body.email)):
                raise HTTPException(409, 'Email já cadastrado.')
            row = await connection.fetchrow('''INSERT INTO access_requests(requested_name,requested_email,temporary_password_hash,
                requested_by,requested_role_id,requested_team_id) VALUES($1,$2,$3,$4,$5,$6) RETURNING *''', body.name, str(body.email), encoded, user['id'], role, team)
            if role_code == 'ADMIN':
                row = await approve_request(connection, row, user['id'])
                await audit(connection, user['id'], 'USER_CREATED', 'users', row['user_id'], request_id=request.state.request_id)
            await audit(connection, user['id'], 'ACCESS_REQUEST_CREATED', 'access_requests', row['id'], request_id=request.state.request_id)
            return ApiResponse(data=AccessRequestResponse.model_validate(dict(row), extra='ignore'))
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, 'Já existe uma conta ou solicitação pendente com esse email.') from None


@router.get('', response_model=ApiResponse[ListResponse[AccessRequestResponse]])
async def requests(connection: Connection, query: Annotated[AccessRequestQuery, Query()], user=Depends(Authorization('accounts.request.read'))):
    """Lista pedidos próprios; somente ADMIN consulta todos.

    ADMIN consulta todos os pedidos não excluídos; N2/N3 consultam somente os próprios. Itens e
    total usam o mesmo filtro.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ListResponse[AccessRequestResponse]]: Página sanitizada de pedidos e total
            autorizado.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    role = await connection.fetchval('SELECT code FROM roles WHERE id=$1', user['role_id'])
    actor = None if role == 'ADMIN' else user['id']
    where = 'FROM access_requests WHERE NOT soft_delete AND ($1::uuid IS NULL OR requested_by=$1) AND ($2::text IS NULL OR status=$2)'
    rows = await connection.fetch('SELECT * '+where+' ORDER BY created_at DESC,id LIMIT $3 OFFSET $4', actor, query.status, query.per_page, (query.page-1)*query.per_page)
    return ApiResponse(data={'items':[AccessRequestResponse.model_validate(dict(r), extra='ignore') for r in rows], 'total':await connection.fetchval('SELECT count(*) '+where, actor, query.status)})


@router.get('/{id}', response_model=ApiResponse[AccessRequestResponse])
async def request_detail(id: UUID, connection: Connection, user=Depends(Authorization('accounts.request.read'))):
    """Oculta pedidos de terceiros para solicitantes sem permissão administrativa.

    Seleciona pedido não excluído do próprio solicitante ou de ADMIN. Não retorna o hash da
    temporária.

    Args:
        id: UUID do pedido de acesso.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[AccessRequestResponse]: Dados e decisão do pedido autorizado.

    Raises:
        HTTPException: Status 404 quando o pedido não existe ou não pertence ao escopo.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row = await connection.fetchrow('''SELECT a.* FROM access_requests a WHERE a.id=$1 AND NOT a.soft_delete
        AND (a.requested_by=$2 OR EXISTS(SELECT 1 FROM roles WHERE id=$3 AND code='ADMIN' AND NOT soft_delete))''', id, user['id'], user['role_id'])
    if not row:
        raise HTTPException(404, 'Solicitação não encontrada.')
    return ApiResponse(data=AccessRequestResponse.model_validate(dict(row), extra='ignore'))


@router.post('/{id}/approve', response_model=ApiResponse[AccessRequestResponse], dependencies=[Depends(require_csrf)])
async def approve(id: UUID, request: Request, connection: Connection, user=Depends(Authorization('accounts.approve'))):
    """Reserva vaga e cria conta uma única vez, sob bloqueio transacional.

    Serializa os cadastros com advisory lock e bloqueia o pedido. Aprovação, conta, senha e
    auditoria pertencem à mesma transação.

    Args:
        id: UUID do pedido pendente.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[AccessRequestResponse]: Pedido aprovado com vínculo da nova conta.

    Raises:
        HTTPException: Status 404 para pedido ausente; 409 para pedido já decidido, identidade
            existente ou vaga ocupada; 422 para papel/equipe inválidos.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    try:
        async with connection.transaction():
            await connection.execute('SELECT pg_advisory_xact_lock(827462)')
            row = await connection.fetchrow('SELECT * FROM access_requests WHERE id=$1 AND NOT soft_delete FOR UPDATE', id)
            if not row:
                raise HTTPException(404, 'Solicitação não encontrada.')
            if row['status'] != 'PENDING':
                raise HTTPException(409, 'Solicitação já decidida.')
            row = await approve_request(connection, row, user['id'])
            await audit(connection, user['id'], 'ACCESS_REQUEST_APPROVED', 'access_requests', id, request_id=request.state.request_id)
            return ApiResponse(data=AccessRequestResponse.model_validate(dict(row), extra='ignore'))
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, 'Email já cadastrado.') from None


@router.post('/{id}/reject', response_model=ApiResponse[AccessRequestResponse], dependencies=[Depends(require_csrf)])
async def reject(id: UUID, body: AccessRequestReject, request: Request, connection: Connection, user=Depends(Authorization('accounts.approve'))):
    """Decide um pedido pendente e descarta seu hash temporário.

    Bloqueia o pedido pendente e registra motivo, autor e data. Remove o hash temporário sem
    criar conta e grava auditoria na mesma transação.

    Args:
        id: UUID do pedido de acesso.
        body: AccessRequestReject validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[AccessRequestResponse]: Pedido rejeitado com motivo autorizado.

    Raises:
        HTTPException: Status 404 para pedido ausente; 409 para decisão já terminal.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await connection.fetchrow('SELECT * FROM access_requests WHERE id=$1 AND NOT soft_delete FOR UPDATE', id)
        if not row:
            raise HTTPException(404, 'Solicitação não encontrada.')
        if row['status'] != 'PENDING':
            raise HTTPException(409, 'Solicitação já decidida.')
        row = await connection.fetchrow('''UPDATE access_requests SET status='REJECTED',temporary_password_hash=NULL,
            rejection_reason=$2,decided_by=$3,decided_at=NOW(),updated_at=NOW(),updated_by=$3 WHERE id=$1 RETURNING *''', id, body.reason, user['id'])
        await audit(connection, user['id'], 'ACCESS_REQUEST_REJECTED', 'access_requests', id, request_id=request.state.request_id)
        return ApiResponse(data=AccessRequestResponse.model_validate(dict(row), extra='ignore'))
