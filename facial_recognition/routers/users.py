"""Endpoint users."""
from typing import Annotated

from fastapi import Depends, Query, APIRouter

from facial_recognition.core import Connection, Authorization
from facial_recognition.schemas.users import UserResponse, UserQuery
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
