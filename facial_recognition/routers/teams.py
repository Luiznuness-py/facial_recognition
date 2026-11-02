"""Endpoint teams."""
from typing import Annotated

from fastapi import Depends, Query, APIRouter

from facial_recognition.schemas.teams import TeamResponse
from facial_recognition.core import Connection, Authorization
from facial_recognition.schemas.base_model import (
    ApiResponse, ListResponse,
    PaginationParams,
)

router = APIRouter(prefix="/teams", tags=["TEAMS"])


@router.get('/', response_model=ApiResponse[ListResponse[TeamResponse]], tags=['Teams'])
async def teams(connection: Connection, pagination: Annotated[PaginationParams, Query()], user=Depends(Authorization('teams.read'))):
    """Lista as equipes vigentes em GET /teams.

    Ordena por código e não devolve informações privadas de usuários ou investigações.

    Args:
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        pagination: Página e tamanho validados pelo schema de paginação.
        user: Conta autenticada com teams.read.

    Returns:
        ApiResponse[ListResponse[TeamResponse]]: Catálogo mínimo paginado e total de equipes
            não excluídas.
    """
    rows = await connection.fetch('SELECT id,code,name,description FROM teams WHERE NOT soft_delete ORDER BY code LIMIT $1 OFFSET $2',pagination.per_page,(pagination.page-1)*pagination.per_page)
    return ApiResponse(data={'items':[dict(row) for row in rows],'total':await connection.fetchval('SELECT count(*) FROM teams WHERE NOT soft_delete')})
