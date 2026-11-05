"""Regras científicas exercitadas pelas rotas com PostgreSQL e permissões reais."""
from uuid import UUID
from time import perf_counter

import pytest

from conftest import activate_admin, mutate
from test_auth_regressions import database_value


class CountConnection:
    """Conta chamadas SQL reais sem substituir a autorização ou as consultas."""
    def __init__(self,connection):
        """Associa a conexão real ao adaptador de sincronização ou contagem do teste.

        Args:
            connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
                indicada.

        Returns:
            None: Adaptador inicializado sem abrir ou fechar a conexão recebida.
        """
        self.connection=connection
        self.count=0

    def __getattr__(self,name):
        """Encaminha atributos e envolve os métodos SQL para contar suas chamadas.

        Args:
            name: Nome do atributo a encaminhar à conexão real encapsulada.

        Returns:
            Any: Atributo original ou função assíncrona que conta e executa o método SQL.

        Raises:
            AttributeError: Quando a conexão real também não possui o atributo solicitado.
        """
        method=getattr(self.connection,name)
        if name not in {'fetch','fetchrow','fetchval','execute'}:
            return method
        async def call(*args,**kwargs):
            """Conta uma chamada SQL e delega os argumentos à conexão original.

            Args:
                args: Argumentos posicionais encaminhados sem alteração à chamada encapsulada.
                kwargs: Argumentos nomeados encaminhados sem alteração à chamada encapsulada.

            Returns:
                Any: Resultado original do método SQL encapsulado.
            """
            self.count+=1
            return await method(*args,**kwargs)
        return call


def test_successive_n3_requests(client,laboratory):
    """Cada envio acompanha seu pedido; a nova tarefa recebe o motivo que a originou.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        laboratory: UUIDs das contas N1/N2 de duas equipes e N3 preparados no fixture.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    people=laboratory
    agent,validation=create_sample(client,people)
    previous=None
    reports=[]
    for reason in ('Primeiro pedido N3','Segundo pedido N3'):
        login_as(client,people['owner'])
        detail=client.get('/api/v1/validations/'+validation).json()['data']
        assert detail['previous_validation_id']==previous
        complete_analysis(client,validation)
        assert mutate(client,'/validations/'+validation+'/submit').status_code==200
        login_as(client,people['supervisor'])
        body=dict(title='Relatório',final_conclusion='Conclusão',final_risk_percentage=0,public_title='Notícia',public_risk_category='LOW',public_body='Texto')
        assert mutate(client,'/validations/'+validation+'/report/send',body).status_code==200
        report=next(r for r in client.get('/api/v1/reports/sent').json()['data']['items'] if r['validation_id']==validation)
        vault=report['vault_id']
        assert report['new_validation_request'] is None
        login_as(client,people['authority'])
        assert mutate(client,'/vault/dossiers/'+vault+'/request-validation',{'reason':reason}).status_code==200
        login_as(client,people['supervisor'])
        report=next(r for r in client.get('/api/v1/reports/sent').json()['data']['items'] if r['vault_id']==vault)
        assert report['new_validation_request']['reason']==reason
        assert report['new_validation_request']['fulfilled_validation_id'] is None
        assert client.get('/api/v1/validations/'+validation).json()['data']['new_validation_request']==detail['new_validation_request']
        created=mutate(client,'/biological-agents/'+agent+'/validations',{'responsible_user_id':people['owner'],'request_vault_id':vault})
        assert created.status_code==201,created.text
        previous,validation=validation,created.json()['data']['id']
        expected=dict(report['new_validation_request'],fulfilled_validation_id=validation)
        assert created.json()['data']['new_validation_request']==expected
        detail=client.get('/api/v1/validations/'+validation).json()['data']
        assert detail['new_validation_request']==expected
        cards=client.get('/api/v1/biological-agents/'+agent+'/validations').json()['data']['items']
        assert next(c for c in cards if c['id']==validation)['new_validation_request']==expected
        reports.append((vault,expected))
        for vault_id,request in reports:
            sent=client.get('/api/v1/reports/sent').json()['data']['items']
            assert next(r for r in sent if r['vault_id']==vault_id)['new_validation_request']==request


def test_sample_list_has_constant_queries_and_historical_edit_rule(client,laboratory):
    """Paginação e exclusão lógica não liberam edição nem criam consulta por item.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        laboratory: UUIDs das contas N1/N2 de duas equipes e N3 preparados no fixture.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    people=laboratory
    agent,validation=create_sample(client,people)
    complete_analysis(client,validation)
    assert mutate(client,'/validations/'+validation+'/submit').status_code==200
    async def prepare():
        """Prepara os registros específicos deste cenário dentro da transação revertida do fixture.

        Returns:
            None: Operação concluída e verificações satisfeitas, quando presentes.
        """
        async with client.app.state.db_pool.acquire() as c:
            await c.execute('UPDATE investigation_submissions SET soft_delete=TRUE WHERE validation_id=$1',UUID(validation))
            await c.execute("UPDATE validations SET soft_delete=TRUE WHERE id=$1",UUID(validation))
            await c.execute('''INSERT INTO biological_agents(code,provisional_label,material_type,collection_location,collected_on,
                initial_observations,investigation_reason,team_id,created_by)
                SELECT 'LIST-'||n,'Sem entrega '||n,'Água','Local',CURRENT_DATE,'Observação','Motivo',team_id,created_by
                FROM biological_agents CROSS JOIN generate_series(1,99) n WHERE id=$1''',UUID(agent))
    client.portal.call(prepare)
    login_as(client,people['supervisor'])
    pool=client.app.state.db_pool
    original=pool.connection
    counted=CountConnection(original)
    pool.connection=counted
    try:
        counts=[]
        elapsed=[]
        for size in (1,100):
            counted.count=0
            started=perf_counter()
            response=client.get('/api/v1/biological-agents?per_page='+str(size))
            elapsed.append(round((perf_counter()-started)*1000,2))
            assert response.status_code==200,response.text
            data=response.json()['data']
            assert data['total']==100 and len(data['items'])==size
            counts.append(counted.count)
        assert counts[0]==counts[1],counts
        assert counts[1]<=5,counts
        print(f'Listagem local, páginas de 1/100 amostras: consultas={counts}; duração_ms={elapsed}')
    finally:
        pool.connection=original
    assert not next(a for a in data['items'] if a['id']==agent)['can_edit']
    assert all(a['can_edit'] for a in data['items'] if a['id']!=agent)
    filtered=client.get('/api/v1/biological-agents?search=Amostra&per_page=1').json()['data']
    assert filtered['total']==1 and not filtered['items'][0]['can_edit']
    assert not client.get('/api/v1/biological-agents/'+agent).json()['data']['can_edit']
    assert patch(client,'/biological-agents/'+agent,{'provisional_label':'Mudança'}).status_code==409


def test_validation_cards_have_constant_queries(client,laboratory):
    """Responsável, última entrega e pedido N3 não geram consultas por card.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        laboratory: UUIDs das contas N1/N2 de duas equipes e N3 preparados no fixture.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    agent,validation=create_sample(client,laboratory)
    async def prepare():
        """Prepara os registros específicos deste cenário dentro da transação revertida do fixture.

        Returns:
            None: Operação concluída e verificações satisfeitas, quando presentes.
        """
        async with client.app.state.db_pool.acquire() as c:
            await c.execute('''INSERT INTO validations(agent_id,team_id,responsible_user_id,created_by,status,
                assessments_performed,observed_results,technical_opinion,recommendation,closed_at,closed_by,closure_cause,closure_reason)
                SELECT agent_id,team_id,responsible_user_id,created_by,'CLOSED','A','B','C','D',NOW(),created_by,'N2_CLOSED','Fim'
                FROM validations CROSS JOIN generate_series(1,99) WHERE id=$1''',UUID(validation))
    client.portal.call(prepare)
    pool=client.app.state.db_pool
    original=pool.connection
    counted=CountConnection(original)
    pool.connection=counted
    try:
        counts=[]
        for size in (1,100):
            counted.count=0
            response=client.get('/api/v1/biological-agents/'+agent+'/validations?per_page='+str(size))
            assert response.status_code==200,response.text
            data=response.json()['data']
            assert data['total']==100 and len(data['items'])==size
            assert all(c['responsible']['id']==laboratory['owner'] for c in data['items'])
            assert all(c['new_validation_request'] is None for c in data['items'])
            counts.append(counted.count)
        assert counts[0]==counts[1],counts
        assert counts[1]<=6,counts
        print(f'Cards de investigação, páginas de 1/100: consultas={counts}')
    finally:
        pool.connection=original
    closed=client.get('/api/v1/biological-agents/'+agent+'/validations?status=CLOSED').json()['data']
    assert closed['total']==99 and all(c['status']=='CLOSED' for c in closed['items'])


@pytest.fixture
def laboratory(client):
    """Prepara contas institucionais; sessão de teste não substitui a autorização SQL.

    Cria as contas via rotas administrativas e habilita o fixture para testes científicos. As
    alterações pertencem à transação externa revertida pelo cliente.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.

    Returns:
        dict[str, str]: UUIDs dos atores identificados por seu papel no cenário.
    """
    activate_admin(client)
    teams = client.get('/api/v1/teams').json()['data']['items']
    people = {}
    for name,role,team in [('owner','N1',0),('colleague','N1',0),('supervisor','N2',0),('outsider','N1',1),('other_supervisor','N2',1),('authority','N3',None)]:
        body = dict(name=name,email=name+'@example.com',role_code=role,temporary_password='Temporary!Person2026')
        if team is not None:
            body['team_id']=teams[team]['id']
        response = mutate(client,'/access-requests',body)
        assert response.status_code==201,response.text
        people[name]=response.json()['data']['user_id']
    async def prepare():
        """Contas ativas de fixture permitem testar negócio sem repetir toda a ativação.

        Returns:
            None: Operação concluída e verificações satisfeitas, quando presentes.
        """
        async with client.app.state.db_pool.acquire() as c:
            await c.execute("UPDATE users SET status='ACTIVE',activated_at=NOW(),password_change_required=FALSE,biometric_enrollment_required=FALSE")
    client.portal.call(prepare)
    return people


def login_as(client, id):
    """Cria sessão real no banco para o ator da próxima operação de negócio.

    Insere uma sessão real e substitui os cookies do cliente pelo ACCESS daquele ator. Não
    executa senha ou prova facial; as rotas ainda consultam a autorização no banco.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        id: UUID da conta fictícia que atuará nas próximas requisições.

    Returns:
        None: Cliente preparado para agir como a conta indicada.
    """
    async def session():
        """Insere uma sessão limitada pelo mesmo constraint usado na aplicação.

        Returns:
            UUID: Identificador da sessão recém-criada.
        """
        async with client.app.state.db_pool.acquire() as c:
            return await c.fetchval("INSERT INTO sessions(user_id,expires_at) VALUES($1,NOW()+INTERVAL '24 hours') RETURNING id",UUID(id))
    sid=client.portal.call(session)
    client.cookies.clear()
    client.cookies.set('lab_access',client.app.state.tokens.create_token(UUID(id),'ACCESS',900,session_id=str(sid)),path='/api/v1')


def patch(client,path,body):
    """Envia alteração com proteção CSRF real.

    Obtém CSRF atual e envia Origin da mesma origem antes do PATCH. Preserva a resposta completa
    para as asserções do chamador.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        path: Caminho HTTP relativo usado pela requisição do cenário.
        body: Corpo JSON do PATCH; None é encaminhado sem criação de dados fictícios.

    Returns:
        httpx.Response: Resultado da alteração, inclusive recusas esperadas.
    """
    csrf=client.get('/api/v1/auth/csrf').json()['data']['csrf_token']
    return client.patch('/api/v1'+path,json=body,headers={'Origin':'https://testserver','X-CSRF-Token':csrf})


def create_sample(client, people):
    """Cria amostra e investigação pelo responsável N1.

    Entra como o N1 responsável e cadastra amostra e primeira investigação pelas rotas reais. O
    chamador recebe os identificadores para continuar o cenário.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        people: Mapa de UUIDs das contas institucionais preparado pelo fixture laboratory.

    Returns:
        tuple[str, str]: UUIDs da amostra e da primeira investigação.
    """
    login_as(client,people['owner'])
    response=mutate(client,'/biological-agents',dict(provisional_label='Amostra A',material_type='Água',collection_location='Local reservado',collected_on='2026-01-01',initial_observations='Observações',investigation_reason='Investigar'))
    assert response.status_code==201,response.text
    data=response.json()['data']
    return data['agent']['id'],data['validation']['id']


def complete_analysis(client,id):
    """Preenche os quatro textos obrigatórios e preserva zero como risco válido.

    Envia PATCH com os quatro textos e risco zero e exige sucesso. Não submete a entrega; mantém
    o rascunho editável.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        id: UUID da investigação cujo rascunho receberá os quatro textos e risco zero.

    Returns:
        None: Formulário mínimo completo persistido no fixture.
    """
    response=patch(client,'/validations/'+id+'/analysis',dict(assessments_performed='Avaliação',observed_results='Resultado',technical_opinion='Parecer',recommendation='Recomendação',estimated_risk_percentage=0))
    assert response.status_code==200,response.text


def test_samples_scope_analysis_and_history(client,laboratory):
    """Impede acesso de outra equipe, envio incompleto, edição tardia e duplo envio.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        laboratory: UUIDs das contas N1/N2 de duas equipes e N3 preparados no fixture.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    people=laboratory
    a,v=create_sample(client,people)
    assert client.get('/api/v1/biological-agents').json()['data']['total']==1
    assert client.get('/api/v1/biological-agents/'+a).json()['data']['can_edit']
    assert mutate(client,'/validations/'+v+'/submit').status_code==422
    complete_analysis(client,v)
    sent=mutate(client,'/validations/'+v+'/submit')
    assert sent.status_code==200,sent.text
    assert mutate(client,'/validations/'+v+'/submit').status_code==409
    assert patch(client,'/validations/'+v+'/analysis',{'recommendation':'Mudança'}).status_code==409
    assert patch(client,'/biological-agents/'+a,{'provisional_label':'Mudança'}).status_code==409
    assert not client.get('/api/v1/biological-agents/'+a).json()['data']['can_edit']
    login_as(client,people['outsider'])
    assert client.get('/api/v1/biological-agents').json()['data']['total']==0
    assert client.get('/api/v1/validations/'+v).status_code==404
    login_as(client,people['supervisor'])
    assert patch(client,'/biological-agents/'+a+'/status',{'status':'INACTIVE'}).status_code==409
    assert mutate(client,'/biological-agents/'+a+'/validations',{'responsible_user_id':people['owner']}).status_code==409
    returned=mutate(client,'/validations/'+v+'/return',{'reason':'Corrigir'})
    assert returned.status_code==200,returned.text
    login_as(client,people['owner'])
    complete_analysis(client,v)
    assert mutate(client,'/validations/'+v+'/submit').status_code==200
    data=client.get('/api/v1/validations/'+v).json()['data']
    assert len(data['submissions'])==2 and data['submissions'][0]['return_reason']=='Corrigir'
    login_as(client,people['supervisor'])
    assert mutate(client,'/validations/'+v+'/close',{'reason':'Encerramento'}).status_code==200
    assert patch(client,'/biological-agents/'+a+'/status',{'status':'INACTIVE'}).status_code==200
    assert mutate(client,'/biological-agents/'+a+'/validations',{'responsible_user_id':people['owner']}).status_code==409
    assert patch(client,'/biological-agents/'+a+'/status',{'status':'ACTIVE'}).status_code==200
    fresh=mutate(client,'/biological-agents/'+a+'/validations',{'responsible_user_id':people['owner']})
    assert fresh.status_code==201,fresh.text
    login_as(client,people['owner'])
    assert not client.get('/api/v1/biological-agents/'+a).json()['data']['can_edit']


def test_participants_and_responsible(client,laboratory):
    """Colaborador lê sem editar; remoção revoga vínculo e troca preserva anterior.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        laboratory: UUIDs das contas N1/N2 de duas equipes e N3 preparados no fixture.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    people=laboratory
    a,v=create_sample(client,people)
    assert mutate(client,'/validations/'+v+'/participants',{'user_id':people['outsider']}).status_code==422
    added=mutate(client,'/validations/'+v+'/participants',{'user_id':people['colleague']})
    assert added.status_code==201,added.text
    login_as(client,people['colleague'])
    assert client.get('/api/v1/validations/'+v).status_code==200
    assert patch(client,'/validations/'+v+'/analysis',{'recommendation':'Não pode'}).status_code==403
    assert mutate(client,'/validations/'+v+'/participants',{'user_id':people['owner']}).status_code==403
    login_as(client,people['supervisor'])
    csrf=client.get('/api/v1/auth/csrf').json()['data']['csrf_token']
    removed=client.delete('/api/v1/validations/'+v+'/participants/'+people['colleague'],headers={'Origin':'https://testserver','X-CSRF-Token':csrf})
    assert removed.status_code==204,removed.text
    login_as(client,people['colleague'])
    assert client.get('/api/v1/validations/'+v).status_code==404
    login_as(client,people['supervisor'])
    changed=patch(client,'/validations/'+v+'/responsible',{'responsible_user_id':people['colleague']})
    assert changed.status_code==200,changed.text
    assert any(p['user_id']==people['owner'] for p in changed.json()['data']['participants'])
    login_as(client,people['owner'])
    assert patch(client,'/validations/'+v+'/analysis',{'recommendation':'Não pode mais'}).status_code==403


@pytest.mark.parametrize('decision',['publish','keep-restricted','request-validation'])
def test_vault_decisions_public_projection_and_new_work(client,laboratory,decision):
    """Cobre os três destinos terminais, sigilo, idempotência e atendimento de pedido N3.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        laboratory: UUIDs das contas N1/N2 de duas equipes e N3 preparados no fixture.
        decision: Ação N3 parametrizada: publicar, manter sigilo ou solicitar investigação.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    people=laboratory
    a,v=create_sample(client,people)
    complete_analysis(client,v)
    assert mutate(client,'/validations/'+v+'/submit').status_code==200
    login_as(client,people['supervisor'])
    body=dict(title='Relatório privado',final_conclusion='Conclusão reservada',final_risk_percentage=17.25,public_title='Notícia pública',public_subtitle='Resumo',public_risk_category='HIGH',public_body='Texto autorizado')
    sent=mutate(client,'/validations/'+v+'/report/send',body)
    assert sent.status_code==200,sent.text
    assert mutate(client,'/validations/'+v+'/report/send',body).status_code==409
    report=client.get('/api/v1/reports/sent').json()['data']['items'][0]
    vault_id=report['vault_id']
    assert str(database_value(client,"SELECT resource_id FROM audit_events WHERE event='REPORT_SENT'"))==vault_id
    assert 'final_conclusion' not in report and 'received_snapshot' not in report
    assert client.get('/api/v1/vault/dossiers/'+vault_id).status_code==403
    assert mutate(client,'/biological-agents/'+a+'/validations',{'responsible_user_id':people['owner']}).status_code==409
    login_as(client,people['authority'])
    listing=client.get('/api/v1/vault/dossiers')
    assert listing.status_code==200,listing.text
    detail=client.get('/api/v1/vault/dossiers/'+vault_id)
    assert detail.status_code==200,detail.text
    assert detail.json()['data']['final_conclusion']=='Conclusão reservada'
    result=mutate(client,'/vault/dossiers/'+vault_id+'/'+decision,None if decision=='publish' else {'reason':'Motivo reservado'})
    assert result.status_code==200,result.text
    assert mutate(client,'/vault/dossiers/'+vault_id+'/keep-restricted',{'reason':'Outra decisão'}).status_code==409
    if decision=='publish':
        id=result.json()['data']['id']
        repeated=mutate(client,'/vault/dossiers/'+vault_id+'/publish')
        assert repeated.json()['data']==result.json()['data']
        public=client.get('/api/v1/public/publications/'+id)
        assert public.status_code==200,public.text
        assert set(public.json()['data'])=={'id','title','subtitle','risk_category','body','published_at'}
        assert client.get('/api/v1/publications/'+id).status_code==200
        assert client.get('/api/v1/publications').json()['data']['total']==1
        withdrawn=mutate(client,'/publications/'+id+'/withdraw',{'reason':'Motivo de retirada reservado'})
        assert withdrawn.status_code==200,withdrawn.text
        assert mutate(client,'/publications/'+id+'/withdraw',{'reason':'Não substitui'}).json()['data']==withdrawn.json()['data']
        assert client.get('/api/v1/public/publications/'+id).status_code==404
        assert client.get('/api/v1/public/publications').json()['data']['total']==0
        assert mutate(client,'/vault/dossiers/'+vault_id+'/publish').status_code==409
    login_as(client,people['supervisor'])
    tracked=client.get('/api/v1/reports/sent').json()['data']['items'][0]
    assert 'Motivo reservado' not in str(tracked) if decision=='keep-restricted' else True
    if decision=='request-validation':
        assert tracked['new_validation_request']['reason']=='Motivo reservado'
        assert mutate(client,'/biological-agents/'+a+'/validations',{'responsible_user_id':people['owner']}).status_code==409
        fresh=mutate(client,'/biological-agents/'+a+'/validations',{'responsible_user_id':people['owner'],'request_vault_id':vault_id})
        assert fresh.status_code==201,fresh.text

        assert fresh.json()['data']['new_validation_request']['fulfilled_validation_id']==fresh.json()['data']['id']
    elif decision=='publish':
        assert tracked['decision_status']=='WITHDRAWN'
    else:
        assert tracked['new_validation_request'] is None
        fresh=mutate(client,'/biological-agents/'+a+'/validations',{'responsible_user_id':people['owner']})
        assert fresh.status_code==201,fresh.text


def test_candidates_participants_and_task_isolation(client,laboratory):
    """Catálogos respeitam equipe, vínculo e soft_delete sem abrir outras tarefas.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        laboratory: UUIDs das contas N1/N2 de duas equipes e N3 preparados no fixture.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    people=laboratory
    a,v=create_sample(client,people)
    assert patch(client,'/biological-agents/'+a,{'known_information':'Informação nova'}).status_code==200
    candidates=client.get('/api/v1/validations/'+v+'/participant-candidates').json()['data']
    assert {p['id'] for p in candidates['items']}=={people['colleague']}
    assert mutate(client,'/validations/'+v+'/participants',{'user_id':people['outsider']}).status_code==422
    assert mutate(client,'/validations/'+v+'/participants',{'user_id':people['colleague']}).status_code==201
    response=client.get('/api/v1/validations/'+v+'/participants')
    assert response.status_code==200,response.text
    assert {p['user_id'] for p in response.json()['data']}=={people['colleague']}
    assert set(response.json()['data'][0])=={'user_id','name','added_by','added_at'}
    complete_analysis(client,v)
    assert mutate(client,'/validations/'+v+'/submit').status_code==200
    login_as(client,people['supervisor'])
    assert mutate(client,'/validations/'+v+'/close',{'reason':'Finalizado'}).status_code==200
    candidates=client.get('/api/v1/biological-agents/'+a+'/responsible-candidates').json()['data']
    assert {p['id'] for p in candidates['items']}=={people['owner'],people['colleague']}
    assert patch(client,'/biological-agents/'+a+'/status',{'status':'INACTIVE'}).status_code==200
    assert mutate(client,'/biological-agents/'+a+'/validations',{'responsible_user_id':people['owner']}).status_code==409
    assert patch(client,'/biological-agents/'+a+'/status',{'status':'ACTIVE'}).status_code==200
    fresh=mutate(client,'/biological-agents/'+a+'/validations',{'responsible_user_id':people['owner']})
    assert fresh.status_code==201,fresh.text
    login_as(client,people['colleague'])
    assert client.get('/api/v1/validations/'+v).status_code==200
    assert client.get('/api/v1/validations/'+fresh.json()['data']['id']).status_code==404
    cards=client.get('/api/v1/biological-agents/'+a+'/validations').json()['data']
    assert cards['total']==1 and cards['items'][0]['id']==v
    login_as(client,people['outsider'])
    assert client.get('/api/v1/validations/'+v+'/participants').status_code==404
    login_as(client,people['owner'])
    database_value(client,'UPDATE investigation_submissions SET soft_delete=TRUE')
    assert not client.get('/api/v1/biological-agents/'+a).json()['data']['can_edit']
    assert patch(client,'/biological-agents/'+a,{'known_information':'Alteração tardia'}).status_code==409


def test_vault_remains_n3_only_with_misconfigured_permissions(client,laboratory):
    """Conceder permissões por engano não libera cofre ou decisões para outro papel.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        laboratory: UUIDs das contas N1/N2 de duas equipes e N3 preparados no fixture.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    people=laboratory
    database_value(client,"""INSERT INTO role_permissions(role_id,permission_id)
        SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code='N2' AND p.code IN ('vault.read','vault.decide','publications.read','publications.publish')
        ON CONFLICT DO NOTHING""")
    login_as(client,people['supervisor'])
    id='00000000-0000-0000-0000-000000000001'
    for path in ['/vault/dossiers','/vault/dossiers/'+id,'/publications','/publications/'+id]:
        assert client.get('/api/v1'+path).status_code==403
    assert mutate(client,'/vault/dossiers/'+id+'/publish').status_code==403
    for action in ['keep-restricted','request-validation']:
        assert mutate(client,'/vault/dossiers/'+id+'/'+action,{'reason':'Não permitido'}).status_code==403
    assert mutate(client,'/publications/'+id+'/withdraw',{'reason':'Não permitido'}).status_code==403
