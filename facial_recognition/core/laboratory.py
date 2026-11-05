"""Acesso e operações compartilhadas do laboratório; transações pertencem às rotas."""
import json

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from facial_recognition.schemas.biological_agents import BiologicalAgentResponse
from facial_recognition.schemas.validations import ValidationResponse
from facial_recognition.schemas.investigation_submissions import InvestigationSubmissionResponse
from facial_recognition.utils.utils import audit

ACTIVE_STATES = ('OPEN', 'RETURNED', 'IN_REVIEW', 'REPORTED')
ANALYSIS_FIELDS = ('assessments_performed','observed_results','technical_opinion','recommendation','estimated_risk_percentage')
# A mesma condição é aplicada às listas e ao detalhe; compartilhar uma tarefa não libera as demais.
VALIDATION_SCOPE = '''v.team_id=$2 AND ( $3='N2' OR ($3='N1' AND (v.responsible_user_id=$4 OR EXISTS(
    SELECT 1 FROM validation_participants vp WHERE vp.validation_id=v.id AND vp.user_id=$4 AND NOT vp.soft_delete))))'''


async def agent(connection, id, user, lock=False):
    """Consulta a amostra somente com vínculo em uma investigação ou supervisão da equipe.

    Aplica equipe e vínculo atual do N1; N2 consulta sua equipe. Com lock=True, exige transação
    e bloqueia a amostra antes de alterações conectadas.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        id: UUID da amostra.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.
        lock: Se True, adquire FOR UPDATE OF a até o fim da transação.

    Returns:
        asyncpg.Record: Cadastro vigente e autorizado da amostra.

    Raises:
        HTTPException: Status 404 quando ausente, excluída ou fora do escopo.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row = await connection.fetchrow('''SELECT a.* FROM biological_agents a WHERE a.id=$1 AND NOT a.soft_delete
        AND a.team_id=$2 AND ($3='N2' OR ($3='N1' AND EXISTS(SELECT 1 FROM validations v
        WHERE v.agent_id=a.id AND NOT v.soft_delete AND (v.responsible_user_id=$4 OR EXISTS(
        SELECT 1 FROM validation_participants p WHERE p.validation_id=v.id AND p.user_id=$4 AND NOT p.soft_delete)))))'''+(' FOR UPDATE OF a' if lock else ''), id, user['team_id'], user['role'], user['id'])
    if not row:
        raise HTTPException(404, 'Amostra não encontrada.')
    return row


async def validation(connection, id, user, lock=False):
    """Revalida vínculo atual; alterações serializam primeiro pela amostra.

    Com lock=True, bloqueia primeiro a amostra e depois a investigação, reconsultando a
    autorização após a espera. Compartilhar uma tarefa não libera as demais.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        id: UUID da investigação.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.
        lock: Se True, serializa a escrita pela amostra e pela investigação.

    Returns:
        asyncpg.Record: Investigação vigente autorizada ao ator.

    Raises:
        HTTPException: Status 404 para investigação/amostra ausente, excluída ou sem vínculo
            permitido.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    if lock:
        agent_id = await connection.fetchval('SELECT agent_id FROM validations WHERE id=$1 AND NOT soft_delete', id)
        if not agent_id:
            raise HTTPException(404, 'Investigação não encontrada.')
        await agent(connection, agent_id, user, True)
    row = await connection.fetchrow('SELECT v.* FROM validations v JOIN biological_agents a ON a.id=v.agent_id AND NOT a.soft_delete WHERE v.id=$1 AND NOT v.soft_delete AND '+VALIDATION_SCOPE+(' FOR UPDATE OF v' if lock else ''), id, user['team_id'], user['role'], user['id'])
    if not row:
        raise HTTPException(404, 'Investigação não encontrada.')
    return row


async def agent_response(connection, row, user):
    """Calcula edição considerando inclusive entregas históricas excluídas logicamente.

    Recebe uma amostra já autorizada. Consulta todas as entregas, inclusive de investigações e
    entregas excluídas logicamente; não bloqueia por conta própria.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        row: Registro da amostra previamente obtido com agent.
        user: Conta atual usada para conferir criador N1 ou supervisor N2.

    Returns:
        BiologicalAgentResponse: Cadastro com can_edit calculado para o ator.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    submitted = await connection.fetchval('''SELECT EXISTS(SELECT 1 FROM investigation_submissions s
        JOIN validations v ON v.id=s.validation_id WHERE v.agent_id=$1)''', row['id'])
    return BiologicalAgentResponse.model_validate(dict(row, can_edit=not submitted and (user['role']=='N2' or row['created_by']==user['id'])), extra='ignore')


async def participants(connection, id):
    """Seleciona vínculos atuais de leitura sem incluir dados pessoais sensíveis.

    O chamador autoriza a investigação. Seleciona colaboradores e contas não excluídos,
    preservando added_by/added_at do vínculo.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        id: UUID da investigação previamente autorizada.

    Returns:
        list[dict]: Identificação mínima dos colaboradores atuais, ordenada por inclusão e UUID.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    return [dict(r) for r in await connection.fetch('''SELECT p.user_id,u.name,p.added_by,p.added_at FROM validation_participants p
        JOIN users u ON u.id=p.user_id AND NOT u.soft_delete WHERE p.validation_id=$1 AND NOT p.soft_delete ORDER BY p.added_at,p.user_id''', id)]


async def submission_response(connection, id):
    """Decodifica o snapshot JSON preservado pelo PostgreSQL.

    O chamador garante existência e autorização da entrega. Decodifica participants_snapshot sem
    consultar os nomes atuais das pessoas.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        id: UUID de uma entrega existente, não excluída e já autorizada.

    Returns:
        InvestigationSubmissionResponse: Entrega não excluída e seu snapshot histórico.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row = dict(await connection.fetchrow('SELECT * FROM investigation_submissions WHERE id=$1 AND NOT soft_delete', id))
    row['participants_snapshot'] = json.loads(row['participants_snapshot'])
    return InvestigationSubmissionResponse.model_validate(row, extra='ignore')


async def new_request(connection, validation_id):
    """Projeta o pedido N3 que originou esta investigação, sem pedidos emitidos por ela.

    O chamador autoriza a investigação. Busca exclusivamente request_fulfilled_by_validation_id;
    o pedido emitido pelo próprio dossiê pertence ao acompanhamento de envios.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        validation_id: UUID da investigação que atendeu ao pedido N3.

    Returns:
        dict | None: Motivo, instante e vínculo do pedido de origem, ou None.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row = await connection.fetchrow('''SELECT new_validation_request_reason AS reason,new_validation_requested_at AS requested_at,
        request_fulfilled_by_validation_id AS fulfilled_validation_id FROM vault WHERE NOT soft_delete
        AND decision_status='NEW_VALIDATION_REQUESTED' AND request_fulfilled_by_validation_id=$1''', validation_id)
    return dict(row) if row else None


async def validation_response(connection, row):
    """Monta análise e entregas autorizadas sem conteúdo do cofre.

    Recebe investigação já autorizada e agrega cadastro mínimo, responsável, colaboradores e
    entregas não excluídas. Não inclui relatório, ficha ou motivos reservados do cofre.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        row: Registro da investigação previamente autorizado pelo chamador.

    Returns:
        ValidationResponse: Análise e histórico permitidos para a investigação.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    a = await connection.fetchrow('SELECT id,code,provisional_label FROM biological_agents WHERE id=$1', row['agent_id'])
    responsible = await connection.fetchrow('SELECT id,name FROM users WHERE id=$1', row['responsible_user_id'])
    submissions = await connection.fetch('SELECT id FROM investigation_submissions WHERE validation_id=$1 AND NOT soft_delete ORDER BY submission_number', row['id'])
    return ValidationResponse.model_validate(dict(row, agent=dict(a), responsible=dict(responsible),
        participants=await participants(connection, row['id']), submissions=[await submission_response(connection, s['id']) for s in submissions],
        new_validation_request=await new_request(connection, row['id'])), extra='ignore')


def editable(row, user, responsible=False):
    """Exige estado editável e, para análise, responsabilidade exclusiva do N1.

    Não consulta o banco. Verifica OPEN/RETURNED e, quando exigido, o papel N1 e a
    responsabilidade exclusiva sobre a análise.

    Args:
        row: Investigação atual, revalidada sob lock antes de uma escrita.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.
        responsible: Se True, exige que o ator seja o N1 responsável; False verifica apenas o
            estado.

    Returns:
        None: Ausência de exceção indica que a regra solicitada foi satisfeita.

    Raises:
        HTTPException: Status 403 para ator sem responsabilidade exigida; 409 para estado não
            editável.
    """
    if responsible and (user['role']!='N1' or row['responsible_user_id']!=user['id']):
        raise HTTPException(403, 'Somente o responsável pode alterar ou enviar a análise.')
    if row['status'] not in {'OPEN','RETURNED'}:
        raise HTTPException(409, 'Investigação não permite alterações nesta etapa.')


async def candidate(connection, id, team):
    """Seleciona N1 ativo e habilitado da equipe para responsabilidade ou leitura.

    Exige transação do chamador. Usa FOR SHARE para impedir alterações da conta durante a
    atribuição, permitindo referências de autoria simultâneas.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        id: UUID da pessoa candidata.
        team: UUID da equipe da investigação.

    Returns:
        asyncpg.Record: UUID e nome do N1 ativo, com etapas obrigatórias concluídas.

    Raises:
        HTTPException: Status 422 para conta ausente, desativada, de outro papel/equipe ou com
            etapas pendentes.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    row = await connection.fetchrow('''SELECT u.id,u.name FROM users u JOIN roles r ON r.id=u.role_id AND NOT r.soft_delete
        WHERE u.id=$1 AND u.team_id=$2 AND r.code='N1' AND u.status='ACTIVE' AND NOT u.soft_delete
        AND NOT u.password_change_required AND NOT u.biometric_enrollment_required FOR SHARE OF u''', id, team)
    if not row:
        raise HTTPException(422, 'Escolha N1 ativo da equipe.')
    return row


async def create_validation(connection, a, responsible, actor, request_vault_id=None):
    """Reserva investigação e atende o pedido N3 obrigatório sob lock da amostra.

    Exige transação, lock da amostra e responsável elegível já conferidos. Reserva a única
    investigação em andamento e atende o pedido pendente atomicamente.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        a: Amostra autorizada mantida sob lock pelo chamador.
        responsible: UUID do N1 elegível escolhido para editar a análise.
        actor: UUID da conta que executa a operação e será registrada na autoria.
        request_vault_id: UUID do dossiê com pedido pendente, obrigatório quando existir esse
            pedido; None nos demais casos.

    Returns:
        asyncpg.Record: Nova investigação OPEN, ligada à anterior quando atende pedido N3.

    Raises:
        HTTPException: Status 409 para amostra inativa, investigação em andamento ou pedido
            ausente/incompatível.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    if a['status']!='ACTIVE':
        raise HTTPException(409, 'Reative a amostra antes de abrir uma investigação.')
    if await connection.fetchval('SELECT EXISTS(SELECT 1 FROM validations WHERE agent_id=$1 AND NOT soft_delete AND status=ANY($2::text[]))', a['id'], list(ACTIVE_STATES)):
        raise HTTPException(409, 'Já existe investigação em andamento.')
    pending = await connection.fetchrow('''SELECT x.* FROM vault x JOIN validations v ON v.id=x.validation_id
        WHERE v.agent_id=$1 AND x.decision_status='NEW_VALIDATION_REQUESTED' AND x.request_fulfilled_by_validation_id IS NULL AND NOT x.soft_delete FOR UPDATE OF x''', a['id'])
    if (pending and pending['id']!=request_vault_id) or (request_vault_id and not pending):
        raise HTTPException(409, 'A nova investigação deve atender ao pedido N3 pendente.')
    row = await connection.fetchrow('''INSERT INTO validations(agent_id,team_id,responsible_user_id,created_by,previous_validation_id)
        VALUES($1,$2,$3,$4,$5) RETURNING *''', a['id'], a['team_id'], responsible, actor, pending['validation_id'] if pending else None)
    if pending:
        await connection.execute('UPDATE vault SET request_fulfilled_by_validation_id=$2 WHERE id=$1', pending['id'], row['id'])
    return row


async def submit_analysis(connection, row, user, request_id):
    """Preserva formulário e participantes antes de bloquear a edição para revisão.

    Exige transação e investigação bloqueada pelo chamador. Preserva textos, risco e equipe em
    uma entrega numerada antes de mudar para IN_REVIEW e registrar auditoria.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        row: Investigação atual, autorizada e bloqueada para escrita.
        user: Conta previamente autenticada e autorizada pela dependência da rota ou pelo
            chamador.
        request_id: UUID de correlação gerado pelo servidor para a requisição atual.

    Returns:
        dict: UUID da investigação, estado IN_REVIEW e instante da entrega.

    Raises:
        HTTPException: Status 403 para ator não responsável; 409 para estado incompatível; 422
            para textos incompletos.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    editable(row, user, True)
    if any(not row[f] or not row[f].strip() for f in ANALYSIS_FIELDS[:4]):
        raise HTTPException(422, 'Preencha os quatro textos da análise antes de enviar.')
    people = await participants(connection, row['id'])
    responsible = await connection.fetchrow('SELECT id,name FROM users WHERE id=$1', row['responsible_user_id'])
    snapshot = [dict(user_id=responsible['id'],name=responsible['name'],role_code='N1')]
    snapshot.extend(dict(user_id=p['user_id'],name=p['name'],role_code='N1') for p in people)
    number = await connection.fetchval('SELECT COALESCE(MAX(submission_number),0)+1 FROM investigation_submissions WHERE validation_id=$1', row['id'])
    submitted_at = await connection.fetchval('''INSERT INTO investigation_submissions(validation_id,submission_number,responsible_user_id,submitted_by,
        assessments_performed,observed_results,technical_opinion,recommendation,estimated_risk_percentage,participants_snapshot)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb) RETURNING submitted_at''', row['id'], number, row['responsible_user_id'], user['id'],
        *(row[f] for f in ANALYSIS_FIELDS), json.dumps(jsonable_encoder(snapshot)))
    await connection.execute("UPDATE validations SET status='IN_REVIEW',updated_at=NOW(),updated_by=$2 WHERE id=$1", row['id'], user['id'])
    await audit(connection, user['id'], 'ANALYSIS_SUBMITTED', 'validations', row['id'], request_id=request_id)
    return dict(id=row['id'],status='IN_REVIEW',submitted_at=submitted_at)
