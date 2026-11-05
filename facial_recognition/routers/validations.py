"""Análise, compartilhamento e revisão de investigações autorizadas."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from facial_recognition.core import Connection, Authorization
from facial_recognition.core import laboratory as lab
from facial_recognition.core.security import require_csrf
from facial_recognition.schemas.base_model import ApiResponse, ListResponse
from facial_recognition.schemas.validations import (
    ValidationResponse, ValidationAnalysisUpdate, ValidationSubmitResponse, ValidationReturn, ValidationReturnResponse,
    ValidationClose, ValidationCloseResponse, ValidationResponsibleUpdate, ValidationResponsibleResponse,
)
from facial_recognition.schemas.validation_participants import ValidationParticipantAdd, ValidationParticipantResponse
from facial_recognition.schemas.users import UserCandidateQuery, UserSummary
from facial_recognition.utils.utils import audit

router = APIRouter(prefix='/validations', tags=['Investigations'])


@router.get('/{id}/participants', response_model=ApiResponse[list[ValidationParticipantResponse]])
async def participants(id: UUID, connection: Connection, user=Depends(Authorization('validations.read'))):
    """Lista colaboradores atuais após conferir acesso à investigação.

    Autoriza a investigação antes de selecionar colaboradores e contas não excluídos. Não
    devolve a análise nem informações de credenciais.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[list[ValidationParticipantResponse]]: Colaboradores atuais, sem o
            responsável.

    Raises:
        HTTPException: Status 404 para investigação ausente ou fora do escopo.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    await lab.validation(connection,id,user)
    return ApiResponse(data=await lab.participants(connection,id))


@router.get('/{id}', response_model=ApiResponse[ValidationResponse])
async def detail(id: UUID, connection: Connection, user=Depends(Authorization('validations.read'))):
    """Lê investigação autorizada e suas entregas, sem relatório selado.

    Consulta equipe e vínculo atual e projeta análise, participantes, entregas e pedido que
    originou a tarefa, sem conteúdo selado.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ValidationResponse]: Investigação e histórico autorizado.

    Raises:
        HTTPException: Status 404 para investigação/amostra ausente, excluída ou sem acesso.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    return ApiResponse(data=await lab.validation_response(connection,await lab.validation(connection,id,user)))


@router.patch('/{id}/analysis', response_model=ApiResponse[ValidationResponse], dependencies=[Depends(require_csrf)])
async def analysis(id: UUID, body: ValidationAnalysisUpdate, request: Request, connection: Connection, user=Depends(Authorization('analyses.write'))):
    """Salva rascunho parcial somente para o N1 responsável em OPEN ou RETURNED.

    Bloqueia amostra/investigação, exige N1 responsável e estado OPEN/RETURNED e altera apenas
    os campos enviados. Salva rascunhos incompletos sem criar entrega.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        body: ValidationAnalysisUpdate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ValidationResponse]: Investigação após salvar o rascunho e auditar.

    Raises:
        HTTPException: Status 404 para recurso fora do escopo; 403 para ator não responsável;
            409 para estado não editável.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await lab.validation(connection,id,user,True)
        lab.editable(row,user,True)
        values = body.model_dump(exclude_unset=True)
        fields = list(values)
        assignments = ','.join(f'{field}=${i+2}' for i,field in enumerate(fields))
        await connection.execute('UPDATE validations SET '+assignments+f',updated_at=NOW(),updated_by=${len(fields)+2} WHERE id=$1',id,*values.values(),user['id'])
        await audit(connection,user['id'],'ANALYSIS_SAVED','validations',id,request_id=request.state.request_id)
        return ApiResponse(data=await lab.validation_response(connection,await lab.validation(connection,id,user)))


@router.post('/{id}/submit', response_model=ApiResponse[ValidationSubmitResponse], dependencies=[Depends(require_csrf)])
async def submit(id: UUID, request: Request, connection: Connection, user=Depends(Authorization('analyses.write'))):
    """Entrega uma cópia preservada e bloqueia nova edição ou envio duplicado.

    Bloqueia amostra/investigação e exige quatro textos completos do N1 responsável. Preserva
    entrega numerada e snapshot da equipe antes de mudar para IN_REVIEW.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ValidationSubmitResponse]: UUID, estado IN_REVIEW e instante da entrega.

    Raises:
        HTTPException: Status 404 para recurso fora do escopo; 403 para ator não responsável;
            409 para estado incompatível; 422 para textos incompletos.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await lab.validation(connection,id,user,True)
        return ApiResponse(data=await lab.submit_analysis(connection,row,user,request.state.request_id))


@router.get('/{id}/participant-candidates', response_model=ApiResponse[ListResponse[UserSummary]])
async def participant_candidates(id: UUID, connection: Connection, query: Annotated[UserCandidateQuery, Query()], user=Depends(Authorization('validations.share'))):
    """Lista colaboradores elegíveis, excluindo responsável e vínculos já presentes.

    Exige tarefa editável e responsabilidade quando o ator é N1. Seleciona N1 ativos da equipe,
    excluindo responsável e vínculos já vigentes.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        query: Schema de consulta com filtros e paginação já validados pelo FastAPI.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ListResponse[UserSummary]]: Página de candidatos à colaboração e total.

    Raises:
        HTTPException: Status 404 para recurso fora do escopo; 403 para N1 não responsável; 409
            para estado não editável.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row = await lab.validation(connection,id,user)
    lab.editable(row,user,user['role']=='N1')
    where = '''FROM users u JOIN roles r ON r.id=u.role_id AND NOT r.soft_delete WHERE u.team_id=$1 AND r.code='N1'
        AND u.status='ACTIVE' AND NOT u.soft_delete AND NOT u.password_change_required AND NOT u.biometric_enrollment_required
        AND u.id<>$2 AND NOT EXISTS(SELECT 1 FROM validation_participants p WHERE p.validation_id=$3 AND p.user_id=u.id AND NOT p.soft_delete)
        AND ($4::text IS NULL OR u.name ILIKE '%'||$4||'%')'''
    args = (row['team_id'],row['responsible_user_id'],id,query.search)
    rows = await connection.fetch('SELECT u.id,u.name '+where+' ORDER BY u.name,u.id LIMIT $5 OFFSET $6',*args,query.per_page,(query.page-1)*query.per_page)
    return ApiResponse(data={'items':[dict(r) for r in rows],'total':await connection.fetchval('SELECT count(*) '+where,*args)})


@router.post('/{id}/participants', response_model=ApiResponse[ValidationParticipantResponse], status_code=201, dependencies=[Depends(require_csrf)])
async def add_participant(id: UUID, body: ValidationParticipantAdd, request: Request, connection: Connection, user=Depends(Authorization('validations.share'))):
    """Inclui ou restaura leitura sem conceder edição e sem apagar a autoria original.

    Bloqueia amostra/investigação e mantém o candidato sob FOR SHARE. Cria ou restaura o vínculo
    em OPEN/RETURNED, preservando autoria/data originais e auditando a ação.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        body: ValidationParticipantAdd validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ValidationParticipantResponse]: Colaborador incluído ou restaurado.

    Raises:
        HTTPException: Status 404 para recurso fora do escopo; 403 para N1 não responsável; 409
            para estado/vínculo incompatível; 422 para candidato inelegível.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await lab.validation(connection,id,user,True)
        lab.editable(row,user,user['role']=='N1')
        person = await lab.candidate(connection,body.user_id,row['team_id'])
        if body.user_id==row['responsible_user_id']:
            raise HTTPException(409, 'Responsável já tem acesso.')
        existing = await connection.fetchrow('SELECT * FROM validation_participants WHERE validation_id=$1 AND user_id=$2',id,body.user_id)
        if existing and not existing['soft_delete']:
            raise HTTPException(409, 'Colaborador já incluído.')
        p = await connection.fetchrow('''INSERT INTO validation_participants(validation_id,user_id,added_by) VALUES($1,$2,$3)
            ON CONFLICT(validation_id,user_id) DO UPDATE SET soft_delete=FALSE RETURNING user_id,added_by,added_at''',id,body.user_id,user['id'])
        await audit(connection,user['id'],'PARTICIPANT_ADDED','validations',id,request_id=request.state.request_id)
        return ApiResponse(data=dict(p,name=person['name']))


@router.delete('/{id}/participants/{user_id}', status_code=204, dependencies=[Depends(require_csrf)])
async def remove_participant(id: UUID, user_id: UUID, request: Request, connection: Connection, user=Depends(Authorization('validations.participants.manage'))):
    """Remove somente o vínculo atual de leitura; entregas históricas permanecem intactas.

    Exige N2, tarefa editável e vínculo vigente diferente do responsável. Marca somente o
    vínculo atual como excluído e audita, sem modificar snapshots.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        user_id: UUID do colaborador cujo vínculo atual será removido.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        Response: HTTP 204 sem corpo após a exclusão lógica do vínculo.

    Raises:
        HTTPException: Status 404 para recurso/vínculo ausente; 409 para estado não editável ou
            tentativa de remover o responsável.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await lab.validation(connection,id,user,True)
        lab.editable(row,user)
        if user_id==row['responsible_user_id']:
            raise HTTPException(409, 'Não remova o responsável.')
        result = await connection.execute('UPDATE validation_participants SET soft_delete=TRUE WHERE validation_id=$1 AND user_id=$2 AND NOT soft_delete',id,user_id)
        if result=='UPDATE 0':
            raise HTTPException(404, 'Colaborador não encontrado.')
        await audit(connection,user['id'],'PARTICIPANT_REMOVED','validations',id,request_id=request.state.request_id)
        return Response(status_code=204)


@router.patch('/{id}/responsible', response_model=ApiResponse[ValidationResponsibleResponse], dependencies=[Depends(require_csrf)])
async def responsible(id: UUID, body: ValidationResponsibleUpdate, request: Request, connection: Connection, user=Depends(Authorization('validations.participants.manage'))):
    """Troca responsável e mantém o anterior como colaborador em uma transação.

    Bloqueia amostra/investigação e confere novo N1 com FOR SHARE. Em OPEN/RETURNED, mantém o
    anterior como colaborador e remove a colaboração duplicada do novo responsável.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        body: ValidationResponsibleUpdate validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ValidationResponsibleResponse]: Responsável e colaboradores atuais após a
            operação.

    Raises:
        HTTPException: Status 404 para recurso fora do escopo; 409 para estado não editável; 422
            para candidato inelegível.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await lab.validation(connection,id,user,True)
        lab.editable(row,user)
        person = await lab.candidate(connection,body.responsible_user_id,row['team_id'])
        if body.responsible_user_id!=row['responsible_user_id']:
            await connection.execute('''INSERT INTO validation_participants(validation_id,user_id,added_by) VALUES($1,$2,$3)
                ON CONFLICT(validation_id,user_id) DO UPDATE SET soft_delete=FALSE''',id,row['responsible_user_id'],user['id'])
            await connection.execute('UPDATE validation_participants SET soft_delete=TRUE WHERE validation_id=$1 AND user_id=$2',id,body.responsible_user_id)
            await connection.execute('UPDATE validations SET responsible_user_id=$2,updated_by=$3,updated_at=NOW() WHERE id=$1',id,body.responsible_user_id,user['id'])
            await audit(connection,user['id'],'RESPONSIBLE_CHANGED','validations',id,request_id=request.state.request_id)
        return ApiResponse(data={'responsible':dict(person),'participants':await lab.participants(connection,id)})


@router.post('/{id}/return', response_model=ApiResponse[ValidationReturnResponse], dependencies=[Depends(require_csrf)])
async def return_analysis(id: UUID, body: ValidationReturn, request: Request, connection: Connection, user=Depends(Authorization('validations.review'))):
    """Registra a devolução na entrega mais recente e libera correção do rascunho.

    Exige N2 da equipe e IN_REVIEW. Registra motivo/autoria/data na última entrega não excluída,
    muda a tarefa para RETURNED e grava auditoria atomicamente.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        body: ValidationReturn validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ValidationReturnResponse]: UUID, estado RETURNED, motivo e instante da
            devolução.

    Raises:
        HTTPException: Status 404 para recurso fora do escopo; 409 para investigação fora de
            revisão.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await lab.validation(connection,id,user,True)
        if row['status']!='IN_REVIEW':
            raise HTTPException(409, 'Investigação não está em revisão.')
        returned_at = await connection.fetchval('''UPDATE investigation_submissions SET returned_by=$2,returned_at=NOW(),return_reason=$3
            WHERE id=(SELECT id FROM investigation_submissions WHERE validation_id=$1 AND NOT soft_delete ORDER BY submission_number DESC LIMIT 1) RETURNING returned_at''',id,user['id'],body.reason)
        await connection.execute("UPDATE validations SET status='RETURNED',updated_by=$2,updated_at=NOW() WHERE id=$1",id,user['id'])
        await audit(connection,user['id'],'ANALYSIS_RETURNED','validations',id,request_id=request.state.request_id)
        return ApiResponse(data={'id':id,'status':'RETURNED','reason':body.reason,'returned_at':returned_at})


@router.post('/{id}/close', response_model=ApiResponse[ValidationCloseResponse], dependencies=[Depends(require_csrf)])
async def close(id: UUID, body: ValidationClose, request: Request, connection: Connection, user=Depends(Authorization('validations.review'))):
    """Encerra uma revisão sem encaminhá-la ao cofre.

    Exige N2 da equipe e IN_REVIEW. Define encerramento N2_CLOSED com motivo e autoria, libera a
    vaga da amostra e registra auditoria sem criar dossiê.

    Args:
        id: UUID do recurso autorizado que será consultado ou alterado.
        body: ValidationClose validado, com os campos permitidos para esta operação.
        request: Requisição HTTP com cookies, origem e contexto de auditoria quando utilizado.
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.

    Returns:
        ApiResponse[ValidationCloseResponse]: Estado CLOSED e metadados do encerramento.

    Raises:
        HTTPException: Status 404 para recurso fora do escopo; 409 para investigação fora de
            revisão.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    async with connection.transaction():
        row = await lab.validation(connection,id,user,True)
        if row['status']!='IN_REVIEW':
            raise HTTPException(409, 'Investigação não está em revisão.')
        closed = await connection.fetchrow('''UPDATE validations SET status='CLOSED',closed_at=NOW(),closed_by=$2,
            closure_reason=$3,closure_cause='N2_CLOSED',updated_by=$2,updated_at=NOW() WHERE id=$1 RETURNING *''',id,user['id'],body.reason)
        await audit(connection,user['id'],'VALIDATION_CLOSED','validations',id,request_id=request.state.request_id)
        return ApiResponse(data=ValidationCloseResponse.model_validate(dict(closed),extra='ignore'))
