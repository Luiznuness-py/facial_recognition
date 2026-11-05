"""Envios selados, acompanhamento N2 e decisões exclusivas do N3."""
import json
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder

from facial_recognition.core import Connection, Authorization
from facial_recognition.core import laboratory as lab
from facial_recognition.core.security import require_csrf
from facial_recognition.schemas.base_model import ApiResponse, ListResponse
from facial_recognition.schemas.vault import (
    VaultSend, VaultSendResponse, VaultSummary, VaultResponse, VaultQuery,
    VaultDecisionReason, VaultDecisionResponse, SentReportQuery, SentReportResponse,
)
from facial_recognition.schemas.publications import PublicationPublishResponse
from facial_recognition.utils.utils import audit

router = APIRouter(tags=['Reports and vault'])


async def dossier(connection, id, lock=False):
    """Obtém o registro selado; o chamador exige permissão N3.

    O chamador exige permissão N3. Com lock=True, bloqueia a amostra antes do dossiê para
    serializar decisões e novas investigações conectadas.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        id: UUID do dossiê no cofre.
        lock: Se True, exige transação e mantém os locks até seu término.

    Returns:
        asyncpg.Record: Dossiê não excluído, ainda sem projeção de resposta.

    Raises:
        HTTPException: Status 404 para dossiê ausente ou excluído.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    if lock:
        agent_id = await connection.fetchval('SELECT v.agent_id FROM validations v JOIN vault x ON x.validation_id=v.id WHERE x.id=$1 AND NOT x.soft_delete',id)
        if agent_id:
            await connection.fetchval('SELECT id FROM biological_agents WHERE id=$1 FOR UPDATE',agent_id)
    row = await connection.fetchrow('SELECT * FROM vault WHERE id=$1 AND NOT soft_delete'+(' FOR UPDATE' if lock else ''),id)
    if not row:
        raise HTTPException(404, 'Relatório não encontrado.')
    return row


async def summary(connection,row):
    """Identifica o dossiê usando o cadastro preservado no momento do envio.

    Lê a identificação da amostra no received_snapshot, preservando os dados do momento do
    envio. Não consulta nem altera o cadastro atual.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        row: Registro autorizado do cofre contendo received_snapshot em JSON.

    Returns:
        dict: Identificação do dossiê e amostra histórica, para projeção pelo chamador.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    snapshot = json.loads(row['received_snapshot'])
    return {k:row[k] for k in ('id','validation_id','title','protocol','decision_status','sent_at')} | {'agent':snapshot['agent']}


@router.post('/validations/{id}/report/send', response_model=ApiResponse[VaultSendResponse], dependencies=[Depends(require_csrf)])
async def send_report(id: UUID, body: VaultSend, request: Request, connection: Connection, user=Depends(Authorization('reports.send'))):
    """Sela cadastro, entrega, equipe e notícia; não devolve o conteúdo ao N2.

    Exige N2 da equipe e investigação IN_REVIEW. Sela cadastro, equipe, última entrega,
    conclusão e notícia em snapshot; muda para REPORTED e audita na mesma transação.

    Args:
        id: UUID da investigação em revisão.
        body: VaultSend validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[VaultSendResponse]: Metadados do envio, sem devolver o conteúdo selado.

    Raises:
        HTTPException: Status 404 para recurso fora do escopo; 409 para estado incompatível ou
            ausência de entrega.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await lab.validation(connection,id,user,True)
        if row['status']!='IN_REVIEW':
            raise HTTPException(409, 'Investigação não está em revisão.')
        source = await connection.fetchval('SELECT id FROM investigation_submissions WHERE validation_id=$1 AND NOT soft_delete ORDER BY submission_number DESC LIMIT 1',id)
        if not source:
            raise HTTPException(409, 'Não existe entrega para fundamentar o relatório.')
        a = await connection.fetchrow('SELECT * FROM biological_agents WHERE id=$1',row['agent_id'])
        team = await connection.fetchrow('SELECT id,code,name,description FROM teams WHERE id=$1 AND NOT soft_delete',row['team_id'])
        snapshot = dict(agent=dict(a),team=dict(team),submission=(await lab.submission_response(connection,source)).model_dump(mode='json'))
        fields = body.model_dump()
        protocol = 'REL-'+uuid4().hex
        result = await connection.fetchrow('''INSERT INTO vault(validation_id,source_submission_id,protocol,sent_by,received_snapshot,
            title,final_conclusion,final_risk_percentage,public_title,public_subtitle,public_risk_category,public_body)
            VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9,$10,$11,$12) RETURNING id,sent_at''',id,source,protocol,user['id'],
            json.dumps(jsonable_encoder(snapshot)),*(fields[f] for f in ('title','final_conclusion','final_risk_percentage','public_title','public_subtitle','public_risk_category','public_body')))
        await connection.execute("UPDATE validations SET status='REPORTED',updated_at=NOW(),updated_by=$2 WHERE id=$1",id,user['id'])
        await audit(connection,user['id'],'REPORT_SENT','vault',result['id'],request_id=request.state.request_id)
        return ApiResponse(data={'validation_id':id,'status':'REPORTED','protocol':protocol,'sent_at':result['sent_at']})


@router.get('/reports/sent', response_model=ApiResponse[ListResponse[SentReportResponse]])
async def sent_reports(connection: Connection, query: Annotated[SentReportQuery, Query()], user=Depends(Authorization('reports.read'))):
    """N2 acompanha apenas metadados e pedidos da sua equipe, sem ficha ou motivo reservado.

    Restringe à equipe do N2 e projeta identificação mínima do snapshot. Usa o pedido emitido
    pelo próprio dossiê e deriva WITHDRAWN da publicação, sem relatório ou motivos privados.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ListResponse[SentReportResponse]]: Página de envios e total autorizado.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    where = '''FROM vault x JOIN validations v ON v.id=x.validation_id AND NOT v.soft_delete
        LEFT JOIN publications p ON p.vault_id=x.id AND NOT p.soft_delete
        WHERE NOT x.soft_delete AND v.team_id=$1 AND ($2::text IS NULL OR x.title ILIKE '%'||$2||'%' OR x.protocol ILIKE '%'||$2||'%')
        AND ($3::text IS NULL OR CASE WHEN p.status='WITHDRAWN' THEN 'WITHDRAWN' ELSE x.decision_status END=$3)'''
    args = (user['team_id'],query.search,query.decision_status)
    rows = await connection.fetch("SELECT x.*,CASE WHEN p.status='WITHDRAWN' THEN 'WITHDRAWN' ELSE x.decision_status END AS display_status "+where+' ORDER BY x.sent_at DESC,x.id LIMIT $4 OFFSET $5',*args,query.per_page,(query.page-1)*query.per_page)
    items=[]
    for row in rows:
        snapshot=json.loads(row['received_snapshot'])
        pending = dict(reason=row['new_validation_request_reason'],requested_at=row['new_validation_requested_at'],fulfilled_validation_id=row['request_fulfilled_by_validation_id']) if row['decision_status']=='NEW_VALIDATION_REQUESTED' else None
        items.append(dict(vault_id=row['id'],validation_id=row['validation_id'],title=row['title'],agent={k:snapshot['agent'][k] for k in ('id','code','provisional_label')},protocol=row['protocol'],decision_status=row['display_status'],new_validation_request=pending))
    return ApiResponse(data={'items':items,'total':await connection.fetchval('SELECT count(*) '+where,*args)})


@router.get('/vault/dossiers', response_model=ApiResponse[ListResponse[VaultSummary]])
async def dossiers(connection: Connection, query: Annotated[VaultQuery, Query()], user=Depends(Authorization('vault.read'))):
    """Lista os relatórios reservados somente para N3.

    Exige vault.read do N3 e filtra dossiês não excluídos por protocolo/decisão. A identificação
    vem da cópia preservada no envio.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ListResponse[VaultSummary]]: Página privada de metadados do cofre e total.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    where = 'FROM vault WHERE NOT soft_delete AND ($1::text IS NULL OR protocol ILIKE $1) AND ($2::text IS NULL OR decision_status=$2)'
    rows = await connection.fetch('SELECT * '+where+' ORDER BY sent_at DESC,id LIMIT $3 OFFSET $4',query.protocol,query.decision_status,query.per_page,(query.page-1)*query.per_page)
    items=[]
    for row in rows:
        data=await summary(connection,row)
        data['agent']={k:data['agent'][k] for k in ('id','code','provisional_label')}
        items.append(data)
    return ApiResponse(data={'items':items,'total':await connection.fetchval('SELECT count(*) '+where,query.protocol,query.decision_status)})


@router.get('/vault/dossiers/{id}', response_model=ApiResponse[VaultResponse])
async def dossier_detail(id: UUID, connection: Connection, user=Depends(Authorization('vault.read'))):
    """Lê cópia histórica e motivos reservados exclusivamente com permissão de cofre.

    Exige vault.read do N3. Decodifica a cópia recebida e usa sua entrega histórica, sem
    remontar o conteúdo com dados atuais.

    Args:
        id: UUID do dossiê no cofre.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[VaultResponse]: Dossiê completo e motivos reservados autorizados.

    Raises:
        HTTPException: Status 404 para dossiê ausente ou excluído.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row=await dossier(connection,id)
    data=dict(row)
    data['received_snapshot']=json.loads(data['received_snapshot'])
    data['agent']={k:data['received_snapshot']['agent'][k] for k in ('id','code','provisional_label')}
    data['submission']=data['received_snapshot']['submission']
    return ApiResponse(data=VaultResponse.model_validate(data,extra='ignore'))


@router.post('/vault/dossiers/{id}/publish', response_model=ApiResponse[PublicationPublishResponse], dependencies=[Depends(require_csrf)])
async def publish(id: UUID, request: Request, connection: Connection, user=Depends(Authorization('publications.publish'))):
    """Publica a ficha original uma única vez, preservando a primeira data e autoria.

    Bloqueia amostra/dossiê e exige WAITING_N3/REPORTED. Cria a notícia, termina a investigação
    e audita atomicamente; repetir publicação vigente devolve a existente sem duplicar.

    Args:
        id: UUID do dossiê cuja notícia será publicada.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[PublicationPublishResponse]: Publicação criada ou já vigente, com data
            original.

    Raises:
        HTTPException: Status 404 para dossiê ausente; 409 para decisão incompatível,
            investigação fora de REPORTED ou notícia retirada.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row=await dossier(connection,id,True)
        if row['decision_status']=='PUBLISHED':
            publication=await connection.fetchrow('SELECT id,status,published_at FROM publications WHERE vault_id=$1 AND NOT soft_delete',id)
            if publication and publication['status']=='PUBLISHED':
                return ApiResponse(data=dict(publication))
            raise HTTPException(409, 'Notícia retirada não pode ser republicada.')
        if row['decision_status']!='WAITING_N3':
            raise HTTPException(409, 'Relatório já decidido.')
        state=await connection.fetchval('SELECT status FROM validations WHERE id=$1 AND NOT soft_delete FOR UPDATE',row['validation_id'])
        if state!='REPORTED':
            raise HTTPException(409, 'Investigação não aguarda decisão.')
        publication=await connection.fetchrow('''INSERT INTO publications(vault_id,public_title,public_subtitle,public_risk_category,public_body,published_by)
            VALUES($1,$2,$3,$4,$5,$6) RETURNING id,status,published_at''',id,row['public_title'],row['public_subtitle'],row['public_risk_category'],row['public_body'],user['id'])
        await connection.execute("UPDATE vault SET decision_status='PUBLISHED',decided_by=$2,decided_at=NOW() WHERE id=$1",id,user['id'])
        await connection.execute("UPDATE validations SET status='PUBLISHED',updated_at=NOW(),updated_by=$2 WHERE id=$1",row['validation_id'],user['id'])
        await audit(connection,user['id'],'PUBLICATION_CREATED','publications',publication['id'],request_id=request.state.request_id)
        return ApiResponse(data=dict(publication))


async def decide(connection,id,user,reason,new_validation,request_id):
    """Registra uma decisão terminal e libera a vaga sem alterar o relatório selado.

    Exige autorização N3 e transação do chamador. Bloqueia o dossiê pela amostra, registra
    sigilo ou pedido N3 e encerra a investigação sem sobrescrever o relatório.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        id: UUID do dossiê aguardando decisão.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.
        reason: Motivo validado da decisão; o destino determina quem pode consultá-lo.
        new_validation: Se True, compartilha um pedido de nova investigação; False registra
            sigilo exclusivo N3.
        request_id: UUID de correlação gerado pelo servidor para a requisição atual.

    Returns:
        dict: UUIDs do dossiê/investigação, decisão final e estado CLOSED.

    Raises:
        HTTPException: Status 404 para dossiê ausente; 409 para decisão terminal ou investigação
            fora de REPORTED.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row=await dossier(connection,id,True)
    if row['decision_status']!='WAITING_N3':
        raise HTTPException(409, 'Relatório já decidido.')
    state=await connection.fetchval('SELECT status FROM validations WHERE id=$1 AND NOT soft_delete FOR UPDATE',row['validation_id'])
    if state!='REPORTED':
        raise HTTPException(409, 'Investigação não aguarda decisão.')
    status='NEW_VALIDATION_REQUESTED' if new_validation else 'RESTRICTED'
    if new_validation:
        await connection.execute('''UPDATE vault SET decision_status=$2,decided_by=$3,decided_at=NOW(),new_validation_requested_by=$3,
            new_validation_requested_at=NOW(),new_validation_request_reason=$4 WHERE id=$1''',id,status,user['id'],reason)
    else:
        await connection.execute('UPDATE vault SET decision_status=$2,decided_by=$3,decided_at=NOW(),restricted_reason=$4 WHERE id=$1',id,status,user['id'],reason)
    await connection.execute('''UPDATE validations SET status='CLOSED',closed_by=$2,closed_at=NOW(),closure_cause=$3,
        updated_by=$2,updated_at=NOW() WHERE id=$1''',row['validation_id'],user['id'],'N3_NEW_VALIDATION' if new_validation else 'N3_RESTRICTED')
    await audit(connection,user['id'],'VAULT_DECIDED','vault',id,request_id=request_id)
    return dict(vault_id=id,decision_status=status,validation_id=row['validation_id'],status='CLOSED')


@router.post('/vault/dossiers/{id}/keep-restricted', response_model=ApiResponse[VaultDecisionResponse], dependencies=[Depends(require_csrf)])
async def keep_restricted(id: UUID, body: VaultDecisionReason, request: Request, connection: Connection, user=Depends(Authorization('vault.decide'))):
    """Mantém o motivo de sigilo somente no cofre N3.

    Executa a decisão sob transação e mantém o motivo exclusivamente no cofre. Encerra a
    investigação com causa N3_RESTRICTED e preserva o relatório recebido.

    Args:
        id: UUID do dossiê aguardando decisão.
        body: VaultDecisionReason validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[VaultDecisionResponse]: Dossiê RESTRICTED e investigação CLOSED.

    Raises:
        HTTPException: Status 404 para dossiê ausente; 409 para decisão/estado incompatível.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        return ApiResponse(data=await decide(connection,id,user,body.reason,False,request.state.request_id))


@router.post('/vault/dossiers/{id}/request-validation', response_model=ApiResponse[VaultDecisionResponse], dependencies=[Depends(require_csrf)])
async def request_validation(id: UUID, body: VaultDecisionReason, request: Request, connection: Connection, user=Depends(Authorization('vault.decide'))):
    """Encerra a investigação e comunica à equipe somente o motivo do novo trabalho.

    Executa a decisão sob transação, preserva o dossiê e fecha a investigação com causa
    N3_NEW_VALIDATION. O pedido fica pendente para o N2 da equipe.

    Args:
        id: UUID do dossiê que emitirá o pedido.
        body: VaultDecisionReason validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[VaultDecisionResponse]: Dossiê NEW_VALIDATION_REQUESTED e investigação
            CLOSED.

    Raises:
        HTTPException: Status 404 para dossiê ausente; 409 para decisão/estado incompatível.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        return ApiResponse(data=await decide(connection,id,user,body.reason,True,request.state.request_id))
