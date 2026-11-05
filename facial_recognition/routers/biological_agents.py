"""Cadastro e consultas de amostras com escopo por equipe e investigação."""
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, HTTPException

from facial_recognition.core import Connection, Authorization
from facial_recognition.core import laboratory as lab
from facial_recognition.core.security import require_csrf
from facial_recognition.schemas.base_model import ApiResponse, ListResponse
from facial_recognition.schemas.biological_agents import (
    BiologicalAgentCreate, BiologicalAgentCreateResponse, BiologicalAgentResponse, CreatedAgentResponse, InitialValidationResponse,
    BiologicalAgentUpdate, BiologicalAgentStatusUpdate, BiologicalAgentStatusResponse, BiologicalAgentQuery,
)
from facial_recognition.schemas.validations import ValidationCreate, ValidationCreatedResponse, ValidationQuery, ValidationCardResponse
from facial_recognition.schemas.users import UserCandidateQuery, UserSummary
from facial_recognition.utils.utils import audit

router = APIRouter(prefix='/biological-agents', tags=['Samples'])


@router.post('', response_model=ApiResponse[BiologicalAgentCreateResponse], status_code=201, dependencies=[Depends(require_csrf)])
async def create_agent(body: BiologicalAgentCreate, request: Request, connection: Connection, user=Depends(Authorization('agents.create'))):
    """Cria a amostra e a primeira investigação na mesma transação.

    Confere o N1 elegível e deriva equipe/autor da conta. Cadastro, primeira investigação OPEN e
    auditoria são gravados na mesma transação.

    Args:
        body: BiologicalAgentCreate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[BiologicalAgentCreateResponse]: Identificação da amostra e da primeira
            investigação.

    Raises:
        HTTPException: Status 422 quando o criador deixou de ser um N1 habilitado da equipe.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        await lab.candidate(connection, user['id'], user['team_id'])
        fields = body.model_dump()
        a = await connection.fetchrow('''INSERT INTO biological_agents(code,provisional_label,material_type,collection_location,
            collected_on,initial_observations,investigation_reason,known_information,team_id,created_by)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *''', 'AM-'+uuid4().hex,
            *(fields[f] for f in ('provisional_label','material_type','collection_location','collected_on','initial_observations','investigation_reason','known_information')), user['team_id'], user['id'])
        v = await lab.create_validation(connection, a, user['id'], user['id'])
        await audit(connection, user['id'], 'AGENT_CREATED', 'biological_agents', a['id'], request_id=request.state.request_id)
        return ApiResponse(data={'agent':CreatedAgentResponse.model_validate(dict(a),extra='ignore'), 'validation':InitialValidationResponse.model_validate(dict(v),extra='ignore')})


@router.get('', response_model=ApiResponse[ListResponse[BiologicalAgentResponse]])
async def agents(connection: Connection, query: Annotated[BiologicalAgentQuery, Query()], user=Depends(Authorization('agents.read'))):
    """Aplica escopo e total autorizados e calcula edição histórica em uma consulta.

    Restringe N1 às amostras com investigação vinculada e N2 à própria equipe. Calcula can_edit
    com todo o histórico, inclusive excluído, na consulta da página.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ListResponse[BiologicalAgentResponse]]: Cadastros autorizados, flag de
            edição e total filtrado.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    where = '''FROM biological_agents a WHERE NOT a.soft_delete AND a.team_id=$1
        AND ($2='N2' OR ($2='N1' AND EXISTS(SELECT 1 FROM validations v WHERE v.agent_id=a.id AND NOT v.soft_delete
        AND (v.responsible_user_id=$3 OR EXISTS(SELECT 1 FROM validation_participants p WHERE p.validation_id=v.id AND p.user_id=$3 AND NOT p.soft_delete)))))
        AND ($4::text IS NULL OR a.provisional_label ILIKE '%'||$4||'%' OR a.code ILIKE '%'||$4||'%')
        AND ($5::text IS NULL OR a.status=$5)'''
    args = (user['team_id'], user['role'], user['id'], query.search, query.status)
    rows = await connection.fetch('''SELECT a.*,($2='N2' OR a.created_by=$3) AND NOT EXISTS(
        SELECT 1 FROM investigation_submissions s JOIN validations v ON v.id=s.validation_id
        WHERE v.agent_id=a.id) AS can_edit '''+where+' ORDER BY a.created_at DESC,a.id LIMIT $6 OFFSET $7', *args, query.per_page, (query.page-1)*query.per_page)
    return ApiResponse(data={'items':[BiologicalAgentResponse.model_validate(dict(r),extra='ignore') for r in rows], 'total':await connection.fetchval('SELECT count(*) '+where,*args)})


@router.get('/{id}', response_model=ApiResponse[BiologicalAgentResponse])
async def agent_detail(id: UUID, connection: Connection, user=Depends(Authorization('agents.read'))):
    """Consulta cadastro autorizado sem liberar outras investigações da amostra.

    Aplica equipe/vínculo atual e calcula can_edit usando todas as entregas históricas. O
    detalhe cadastral não libera investigações sem vínculo.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[BiologicalAgentResponse]: Cadastro completo e flag de edição para o ator.

    Raises:
        HTTPException: Status 404 para amostra ausente, excluída ou fora do escopo.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    return ApiResponse(data=await lab.agent_response(connection, await lab.agent(connection,id,user),user))


@router.patch('/{id}', response_model=ApiResponse[BiologicalAgentResponse], dependencies=[Depends(require_csrf)])
async def update_agent(id: UUID, body: BiologicalAgentUpdate, request: Request, connection: Connection, user=Depends(Authorization('agents.update'))):
    """Corrige o cadastro somente antes da primeira entrega histórica.

    Bloqueia a amostra e consulta novamente todo o histórico antes de alterar somente campos
    enviados. Preserva omissão/null do schema e grava auditoria na mesma transação.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        body: BiologicalAgentUpdate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[BiologicalAgentResponse]: Cadastro atualizado e flag de edição recalculada.

    Raises:
        HTTPException: Status 404 para amostra fora do escopo; 403 para N1 não criador; 409 se
            já existe entrega histórica.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await lab.agent(connection,id,user,True)
        if user['role']=='N1' and row['created_by']!=user['id']:
            raise HTTPException(403, 'Somente o criador ou supervisor pode corrigir o cadastro.')
        if not (await lab.agent_response(connection,row,user)).can_edit:
            raise HTTPException(409, 'Cadastro preservado após a primeira entrega.')
        values = body.model_dump(exclude_unset=True)
        fields = list(values)
        assignments = ','.join(f'{field}=${i+2}' for i,field in enumerate(fields))
        await connection.execute('UPDATE biological_agents SET '+assignments+f',updated_at=NOW(),updated_by=${len(fields)+2} WHERE id=$1', id,*values.values(),user['id'])
        await audit(connection,user['id'],'AGENT_UPDATED','biological_agents',id,request_id=request.state.request_id)
        return ApiResponse(data=await lab.agent_response(connection,await lab.agent(connection,id,user),user))


@router.patch('/{id}/status', response_model=ApiResponse[BiologicalAgentStatusResponse], dependencies=[Depends(require_csrf)])
async def agent_status(id: UUID, body: BiologicalAgentStatusUpdate, request: Request, connection: Connection, user=Depends(Authorization('agents.manage'))):
    """Inativa somente amostras sem investigação em andamento.

    Bloqueia a amostra da equipe; INACTIVE exige ausência de investigação em andamento. Atualiza
    estado/autoria e registra auditoria sem exclusão física.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        body: BiologicalAgentStatusUpdate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[BiologicalAgentStatusResponse]: UUID e estado ACTIVE/INACTIVE persistido.

    Raises:
        HTTPException: Status 404 para amostra fora do escopo; 409 para inativação com
            investigação em andamento.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        await lab.agent(connection,id,user,True)
        if body.status=='INACTIVE' and await connection.fetchval('SELECT EXISTS(SELECT 1 FROM validations WHERE agent_id=$1 AND NOT soft_delete AND status=ANY($2::text[]))',id,list(lab.ACTIVE_STATES)):
            raise HTTPException(409, 'Existe investigação em andamento.')
        await connection.execute('UPDATE biological_agents SET status=$2,updated_by=$3,updated_at=NOW() WHERE id=$1',id,body.status,user['id'])
        await audit(connection,user['id'],'AGENT_STATUS_CHANGED','biological_agents',id,request_id=request.state.request_id)
        return ApiResponse(data={'id':id,'status':body.status})


@router.get('/{id}/validations', response_model=ApiResponse[ListResponse[ValidationCardResponse]])
async def validations(id: UUID, connection: Connection, query: Annotated[ValidationQuery, Query()], user=Depends(Authorization('validations.read'))):
    """Lista cards autorizados com responsável, última entrega e pedido na mesma consulta.

    Autoriza a amostra e cada tarefa. Projeta responsável, última entrega não excluída e pedido
    N3 de origem na consulta da página, preservando o mesmo escopo no total.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ListResponse[ValidationCardResponse]]: Cards autorizados com flags de
            edição/envio e total.

    Raises:
        HTTPException: Status 404 para amostra ausente, excluída ou fora do escopo.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    await lab.agent(connection,id,user)
    where = '''FROM validations v JOIN users u ON u.id=v.responsible_user_id
        LEFT JOIN LATERAL (SELECT submitted_at,return_reason FROM investigation_submissions
            WHERE validation_id=v.id AND NOT soft_delete ORDER BY submission_number DESC LIMIT 1) s ON TRUE
        LEFT JOIN vault x ON x.request_fulfilled_by_validation_id=v.id AND NOT x.soft_delete AND x.decision_status='NEW_VALIDATION_REQUESTED'
        WHERE v.agent_id=$1 AND NOT v.soft_delete AND '''+lab.VALIDATION_SCOPE+' AND ($5::text IS NULL OR v.status=$5)'
    args = (id,user['team_id'],user['role'],user['id'],query.status)
    rows = await connection.fetch('''SELECT v.*,u.name AS responsible_name,s.submitted_at,s.return_reason,
        x.new_validation_request_reason AS request_reason,x.new_validation_requested_at AS requested_at,
        x.request_fulfilled_by_validation_id AS fulfilled_validation_id '''+where+' ORDER BY v.created_at DESC,v.id LIMIT $6 OFFSET $7',*args,query.per_page,(query.page-1)*query.per_page)
    items = []
    for row in rows:
        responsible = dict(id=row['responsible_user_id'],name=row['responsible_name'])
        pending = dict(reason=row['request_reason'],requested_at=row['requested_at'],fulfilled_validation_id=row['fulfilled_validation_id']) if row['request_reason'] is not None else None
        edit = user['role']=='N1' and row['responsible_user_id']==user['id'] and row['status'] in {'OPEN','RETURNED'}
        items.append(dict(id=row['id'],status=row['status'],responsible=responsible,created_at=row['created_at'],
            latest_submitted_at=row['submitted_at'],return_reason=row['return_reason'],
            closure_reason=row['closure_reason'],can_edit=edit,can_submit=edit,new_validation_request=pending))
    return ApiResponse(data={'items':items,'total':await connection.fetchval('SELECT count(*) '+where,*args)})


@router.post('/{id}/validations', response_model=ApiResponse[ValidationCreatedResponse], status_code=201, dependencies=[Depends(require_csrf)])
async def new_validation(id: UUID, body: ValidationCreate, request: Request, connection: Connection, user=Depends(Authorization('validations.create'))):
    """Abre nova investigação, reservando a vaga e vinculando o pedido N3 quando exigido.

    Bloqueia a amostra, confere o N1 da equipe e reserva a investigação. Se houver pedido N3
    pendente, exige request_vault_id e registra o atendimento atomicamente com a auditoria.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        body: ValidationCreate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ValidationCreatedResponse]: Nova tarefa OPEN e pedido autorizado de origem.

    Raises:
        HTTPException: Status 404 para amostra fora do escopo; 422 para N1 inelegível; 409 para
            estado, vaga ou pedido incompatível.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        a = await lab.agent(connection,id,user,True)
        await lab.candidate(connection,body.responsible_user_id,a['team_id'])
        v = await lab.create_validation(connection,a,body.responsible_user_id,user['id'],body.request_vault_id)
        await audit(connection,user['id'],'VALIDATION_CREATED','validations',v['id'],request_id=request.state.request_id)
        return ApiResponse(data=ValidationCreatedResponse.model_validate(dict(v,new_validation_request=await lab.new_request(connection,v['id'])),extra='ignore'))


@router.get('/{id}/responsible-candidates', response_model=ApiResponse[ListResponse[UserSummary]])
async def responsible_candidates(id: UUID, connection: Connection, query: Annotated[UserCandidateQuery, Query()], user=Depends(Authorization('validations.create'))):
    """Lista N1 habilitados da equipe sem expor o diretório administrativo.

    Autoriza a amostra e lista N1 ativos da equipe sem etapas obrigatórias pendentes. Pesquisa,
    paginação e total não ampliam o escopo do supervisor.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ListResponse[UserSummary]]: Candidatos elegíveis com UUID/nome e total.

    Raises:
        HTTPException: Status 404 para amostra ausente, excluída ou fora do escopo.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    a = await lab.agent(connection,id,user)
    where = '''FROM users u JOIN roles r ON r.id=u.role_id AND NOT r.soft_delete WHERE u.team_id=$1 AND r.code='N1'
        AND u.status='ACTIVE' AND NOT u.soft_delete AND NOT u.password_change_required AND NOT u.biometric_enrollment_required
        AND ($2::text IS NULL OR u.name ILIKE '%'||$2||'%')'''
    rows = await connection.fetch('SELECT u.id,u.name '+where+' ORDER BY u.name,u.id LIMIT $3 OFFSET $4',a['team_id'],query.search,query.per_page,(query.page-1)*query.per_page)
    return ApiResponse(data={'items':[dict(r) for r in rows],'total':await connection.fetchval('SELECT count(*) '+where,a['team_id'],query.search)})
