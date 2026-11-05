"""Projeções pública e N3 das notícias; retirada preserva o conteúdo original."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from facial_recognition.core import Connection, Authorization
from facial_recognition.core.security import require_csrf
from facial_recognition.schemas.base_model import ApiResponse, ListResponse
from facial_recognition.schemas.publications import (
    PublicPublicationResponse, PublicationResponse, PublicPublicationQuery, PublicationQuery,
    PublicationWithdraw, PublicationWithdrawResponse,
)
from facial_recognition.utils.utils import audit

router=APIRouter(tags=['Publications'])
PUBLIC_FIELDS='id,public_title AS title,public_subtitle AS subtitle,public_risk_category AS risk_category,public_body AS body,published_at'
PRIVATE_FIELDS=PUBLIC_FIELDS+',vault_id,status,published_by,withdrawn_by,withdrawn_at,withdrawal_reason'


@router.get('/public/publications', response_model=ApiResponse[ListResponse[PublicPublicationResponse]])
async def public_publications(connection: Connection, query: Annotated[PublicPublicationQuery, Query()]):
    """Lista somente notícias publicadas, sem vínculos ou dados internos.

    Não exige autenticação. Seleciona apenas notícias PUBLISHED e não excluídas, sem equipe,
    relatório, percentual interno ou motivo de retirada.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.

    Returns:
        ApiResponse[ListResponse[PublicPublicationResponse]]: Página pública sanitizada e total
            filtrado.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    where="FROM publications WHERE NOT soft_delete AND status='PUBLISHED' AND ($1::text IS NULL OR public_title ILIKE '%'||$1||'%' OR public_body ILIKE '%'||$1||'%')"
    rows=await connection.fetch('SELECT '+PUBLIC_FIELDS+' '+where+' ORDER BY published_at DESC,id LIMIT $2 OFFSET $3',query.search,query.per_page,(query.page-1)*query.per_page)
    return ApiResponse(data={'items':[dict(r) for r in rows],'total':await connection.fetchval('SELECT count(*) '+where,query.search)})


@router.get('/public/publications/{id}', response_model=ApiResponse[PublicPublicationResponse])
async def public_detail(id: UUID, connection: Connection):
    """Oculta notícias retiradas e registros excluídos mesmo pelo identificador direto.

    Não exige autenticação. Notícia retirada ou excluída recebe a mesma resposta de recurso
    inexistente.

    Args:
        id: UUID da notícia pública.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.

    Returns:
        ApiResponse[PublicPublicationResponse]: Título, subtítulo, categoria, texto e data
            públicos.

    Raises:
        HTTPException: Status 404 para notícia ausente, retirada ou excluída.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row=await connection.fetchrow('SELECT '+PUBLIC_FIELDS+" FROM publications WHERE id=$1 AND NOT soft_delete AND status='PUBLISHED'",id)
    if not row:
        raise HTTPException(404,'Publicação não encontrada.')
    return ApiResponse(data=dict(row))


@router.get('/publications', response_model=ApiResponse[ListResponse[PublicationResponse]])
async def publications(connection: Connection, query: Annotated[PublicationQuery, Query()], user=Depends(Authorization('publications.read'))):
    """N3 consulta publicadas e retiradas, incluindo seus motivos reservados.

    Exige publications.read do N3. Aplica pesquisa/status e exclusão lógica também ao total,
    incluindo metadados de publicação e retirada.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ListResponse[PublicationResponse]]: Página privada de notícias e total.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    where="FROM publications WHERE NOT soft_delete AND ($1::text IS NULL OR public_title ILIKE '%'||$1||'%' OR public_body ILIKE '%'||$1||'%') AND ($2::text IS NULL OR status=$2)"
    rows=await connection.fetch('SELECT '+PRIVATE_FIELDS+' '+where+' ORDER BY published_at DESC,id LIMIT $3 OFFSET $4',query.search,query.status,query.per_page,(query.page-1)*query.per_page)
    return ApiResponse(data={'items':[dict(r) for r in rows],'total':await connection.fetchval('SELECT count(*) '+where,query.search,query.status)})


@router.get('/publications/{id}', response_model=ApiResponse[PublicationResponse])
async def publication_detail(id: UUID, connection: Connection, user=Depends(Authorization('publications.read'))):
    """Seleciona os metadados privados exclusivamente para a autoridade N3.

    Exige publications.read do N3 e seleciona os campos permitidos da notícia e de sua retirada;
    não expõe credenciais ou análise do N1.

    Args:
        id: UUID da publicação.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[PublicationResponse]: Conteúdo e metadados privados autorizados.

    Raises:
        HTTPException: Status 404 para publicação ausente ou excluída.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row=await connection.fetchrow('SELECT '+PRIVATE_FIELDS+' FROM publications WHERE id=$1 AND NOT soft_delete',id)
    if not row:
        raise HTTPException(404,'Publicação não encontrada.')
    return ApiResponse(data=dict(row))


@router.post('/publications/{id}/withdraw', response_model=ApiResponse[PublicationWithdrawResponse], dependencies=[Depends(require_csrf)])
async def withdraw(id: UUID, body: PublicationWithdraw, request: Request, connection: Connection, user=Depends(Authorization('publications.publish'))):
    """Retira a notícia uma vez e mantém autoria, data e motivo da primeira retirada.

    Exige N3 e bloqueia a notícia. A primeira retirada altera estado, motivo, autoria/data e
    auditoria; repetições preservam os metadados e não republicam.

    Args:
        id: UUID da publicação a retirar.
        body: PublicationWithdraw validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[PublicationWithdrawResponse]: UUID, estado WITHDRAWN e instante original da
            retirada.

    Raises:
        HTTPException: Status 404 para publicação ausente ou excluída.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row=await connection.fetchrow('SELECT * FROM publications WHERE id=$1 AND NOT soft_delete FOR UPDATE',id)
        if not row:
            raise HTTPException(404,'Publicação não encontrada.')
        if row['status']=='PUBLISHED':
            row=await connection.fetchrow("UPDATE publications SET status='WITHDRAWN',withdrawn_by=$2,withdrawn_at=NOW(),withdrawal_reason=$3 WHERE id=$1 RETURNING *",id,user['id'],body.reason)
            await audit(connection,user['id'],'PUBLICATION_WITHDRAWN','publications',id,request_id=request.state.request_id)
        return ApiResponse(data={'id':id,'status':'WITHDRAWN','withdrawn_at':row['withdrawn_at']})
