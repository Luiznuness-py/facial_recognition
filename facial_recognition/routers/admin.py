"""Consultas administrativas sem acesso a conteúdo científico."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from facial_recognition.core import Connection, Authorization
from facial_recognition.schemas.base_model import ApiResponse, ListResponse
from facial_recognition.schemas.roles import RoleResponse
from facial_recognition.schemas.permissions import PermissionResponse
from facial_recognition.schemas.audit_events import AuditEventQuery, AuditEventResponse

router = APIRouter(prefix='/admin', tags=['Administration'])


@router.get('/permissions', response_model=ApiResponse[list[PermissionResponse]])
async def permissions(connection: Connection, user=Depends(Authorization('authorization.read'))):
    """Lista somente permissões vigentes para o administrador.

    Consulta somente o catálogo não excluído. A dependência exige authorization.read; a rota não
    concede nem altera permissões.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[list[PermissionResponse]]: Permissões vigentes ordenadas por código.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    rows = await connection.fetch('SELECT id,code,description FROM permissions WHERE NOT soft_delete ORDER BY code')
    return ApiResponse(data=[dict(row) for row in rows])


@router.get('/roles', response_model=ApiResponse[list[RoleResponse]])
async def roles(connection: Connection, user=Depends(Authorization('authorization.read'))):
    """Consulta papéis e vínculos vigentes sem conceder novas permissões.

    Consulta papéis, permissões e associações não excluídos. A dependência exige
    authorization.read e a resposta não contém credenciais.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[list[RoleResponse]]: Papéis vigentes e suas permissões atuais.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    rows = await connection.fetch('SELECT id,code,name,description FROM roles WHERE NOT soft_delete ORDER BY code')
    result = []
    for row in rows:
        linked = await connection.fetch('''SELECT p.id,p.code,p.description FROM permissions p JOIN role_permissions rp
            ON rp.permission_id=p.id AND NOT rp.soft_delete WHERE rp.role_id=$1 AND NOT p.soft_delete ORDER BY p.code''', row['id'])
        result.append(dict(row, permissions=[dict(p) for p in linked]))
    return ApiResponse(data=result)


@router.get('/audit-events', response_model=ApiResponse[ListResponse[AuditEventResponse]])
async def audit_events(connection: Connection, query: Annotated[AuditEventQuery, Query()], user=Depends(Authorization('audit.read'))):
    """Filtra eventos de contas e autenticação, excluindo conteúdo e motivos científicos.

    Restringe recursos a contas e autenticação, aplica período/evento/ator e usa os mesmos
    filtros no total. Não seleciona eventos científicos ou registros excluídos.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ListResponse[AuditEventResponse]]: Página de eventos administrativos
            sanitizados.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    where = '''FROM audit_events WHERE NOT soft_delete AND resource_type IN
        ('users','access_requests','sessions','authentication_attempts','password_hashes','refresh_tokens')
        AND ($1::text IS NULL OR event=$1) AND ($2::uuid IS NULL OR actor_id=$2)
        AND ($3::timestamptz IS NULL OR created_at>=$3) AND ($4::timestamptz IS NULL OR created_at<=$4)'''
    args = (query.event, query.actor_id, query.date_from, query.date_to)
    rows = await connection.fetch('SELECT id,actor_id,event,resource_type,resource_id,success,reason,request_id,created_at '+where+
        ' ORDER BY created_at DESC,id LIMIT $5 OFFSET $6', *args, query.per_page, (query.page-1)*query.per_page)
    total = await connection.fetchval('SELECT count(*) '+where, *args)
    return ApiResponse(data={'items':[dict(row) for row in rows], 'total':total})
