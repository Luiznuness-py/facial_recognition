"""Endpoint access requests."""
import asyncio
from datetime import timedelta
from http import HTTPStatus

import asyncpg
from fastapi import APIRouter, Request
from fastapi import Depends, HTTPException

from facial_recognition.utils.utils import now, audit
from facial_recognition.core import Connection, Authorization
from facial_recognition.schemas.base_model import ApiResponse
from facial_recognition.core.security import hash_password, validate_new_password, require_csrf
from facial_recognition.schemas.access_requests import AccessRequestCreate, AccessRequestResponse


router = APIRouter(prefix="/access-requests", tags=["ACCESS REQUESTS"])


@router.post(
    '',
    response_model=ApiResponse[AccessRequestResponse],
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)], tags=['Accounts']
)
async def create_account(
    body: AccessRequestCreate,
    request: Request,
    connection: Connection,
    admin=Depends(Authorization('accounts.manage')),
):
    """Cria e aprova uma conta institucional diretamente pelo ADMIN.

    POST /access-requests verifica CSRF por dependência e serializa a reserva de posição com
    lock transacional. Cria usuário, hash temporário de 24 horas, pedido aprovado e
    auditoria juntos. Não implementa ainda pedidos pendentes de N2/N3.

    Args:
        body: Nome, email, senha temporária, papel institucional e equipe solicitados.
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        admin: Conta autenticada com accounts.manage.

    Returns:
        ApiResponse[AccessRequestResponse]: Solicitação aprovada vinculada à conta criada.

    Raises:
        HTTPException: 422 para papel/equipe/senha inválidos; 409 para papel indisponível,
            vaga ocupada ou email duplicado.
    """
    if body.role_code is None or (body.role_code in {'N1','N2'}) != (body.team_id is not None):
        raise HTTPException(422, 'Informe o papel; N1 e N2 exigem equipe, N3 não possui equipe.')
    password = body.temporary_password.get_secret_value()
    validate_new_password(password)
    encoded = await asyncio.to_thread(hash_password,password)
    try:
        async with connection.transaction():
            await connection.execute('SELECT pg_advisory_xact_lock(827462)')
            role = await connection.fetchval('SELECT id FROM roles WHERE code=$1 AND NOT soft_delete',body.role_code)
            if role is None:
                raise HTTPException(409,'Papel indisponível.')
            if body.team_id and not await connection.fetchval('SELECT EXISTS(SELECT 1 FROM teams WHERE id=$1 AND NOT soft_delete)',body.team_id):
                raise HTTPException(422,'Equipe inválida.')
            occupied = await connection.fetchval('''SELECT EXISTS(SELECT 1 FROM users WHERE role_id=$1 AND NOT soft_delete
                AND ($2::uuid IS NULL OR team_id=$2))''',role,body.team_id)
            if body.role_code in {'N2','N3'} and occupied:
                raise HTTPException(409,'A posição deste papel já está ocupada.')
            user_id = await connection.fetchval('INSERT INTO users(name,email,role_id,team_id,created_by) VALUES($1,$2,$3,$4,$5) RETURNING id',body.name,str(body.email),role,body.team_id,admin['id'])
            await connection.execute('INSERT INTO password_hashes(user_id,password_hash,is_temporary,temporary_expires_at,created_by) VALUES($1,$2,TRUE,$3,$4)',user_id,encoded,now()+timedelta(hours=24),admin['id'])
            row = await connection.fetchrow('''INSERT INTO access_requests(user_id,requested_name,requested_email,requested_by,requested_role_id,requested_team_id,status,decided_by,decided_at)
                VALUES($1,$2,$3,$4,$5,$6,'APPROVED',$4,NOW()) RETURNING *''',user_id,body.name,str(body.email),admin['id'],role,body.team_id)
            await audit(connection,admin['id'],'USER_CREATED','users',user_id, request_id=request.state.request_id)
            return ApiResponse(data=AccessRequestResponse.model_validate(dict(row),extra='ignore'))
    except asyncpg.UniqueViolationError:
        raise HTTPException(409,'Já existe uma conta ou solicitação com esse email.') from None
