"""Integração administrativa no PostgreSQL, sem inferência real."""
from conftest import activate_admin
from test_auth_regressions import database_value


def test_admin_catalogs_and_audit(client):
    """Exige sessão e filtra vínculos excluídos e eventos científicos.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    assert client.get('/api/v1/admin/roles').status_code == 401
    activate_admin(client)
    roles = client.get('/api/v1/admin/roles')
    assert roles.status_code == 200
    assert {r['code'] for r in roles.json()['data']} == {'ADMIN', 'N1', 'N2', 'N3'}
    assert client.get('/api/v1/admin/permissions').json()['data']
    result = client.get('/api/v1/admin/audit-events').json()['data']
    assert result['total'] > 0
    assert all(r['resource_type'] in {'users','sessions','authentication_attempts','password_hashes','refresh_tokens','access_requests'} for r in result['items'])
    assert client.get('/api/v1/admin/audit-events?date_from=2026-01-02T00:00:00Z&date_to=2026-01-01T00:00:00Z').status_code == 422


def test_access_request_scope_and_decisions(client):
    """N2 pede N1 da própria equipe; ADMIN decide sem expor o hash.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    from conftest import mutate, FINAL_PASSWORD
    from test_auth import frames
    activate_admin(client)
    team = client.get('/api/v1/teams').json()['data']['items'][0]['id']
    created = mutate(client, '/access-requests', dict(name='Supervisor', email='supervisor@example.com', role_code='N2', team_id=team, temporary_password='Temporary!Supervisor2026'))
    assert created.status_code == 201, created.text
    mutate(client, '/auth/logout')
    assert mutate(client, '/auth/login', dict(email='supervisor@example.com', password='Temporary!Supervisor2026')).status_code == 200
    assert mutate(client, '/auth/biometric/enroll', files=frames()).status_code == 200
    assert mutate(client, '/auth/password/complete', dict(new_password=FINAL_PASSWORD, password_confirmation=FINAL_PASSWORD)).status_code == 200
    body = dict(name='Colega', email='colega@example.com', temporary_password='Temporary!Colega2026')
    assert mutate(client, '/access-requests', dict(body, role_code='N3')).status_code == 403
    pending = mutate(client, '/access-requests', body)
    assert pending.status_code == 201, pending.text
    data = pending.json()['data']
    assert data['status'] == 'PENDING' and data['user_id'] is None
    assert 'temporary_password_hash' not in pending.text
    assert mutate(client, '/access-requests', body).status_code == 409
    assert client.get('/api/v1/access-requests').json()['data']['total'] == 1
    assert client.get('/api/v1/admin/roles').status_code == 403
    assert mutate(client, f"/access-requests/{data['id']}/approve").status_code == 403
    mutate(client, '/auth/logout')
    assert mutate(client, '/auth/login', dict(email='admin@example.com', password=FINAL_PASSWORD)).status_code == 200
    approved = mutate(client, f"/access-requests/{data['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()['data']['user_id']
    assert mutate(client, f"/access-requests/{data['id']}/approve").status_code == 409
    assert mutate(client, f"/access-requests/{data['id']}/reject", {'reason':'Duplicado'}).status_code == 409


def test_account_lifecycle_and_position(client):
    """Valida consulta, edição, desativação, restauração e revalidação da mesma senha.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    from conftest import mutate
    activate_admin(client)
    team = client.get('/api/v1/teams').json()['data']['items'][0]['id']
    body = dict(name='Supervisor', email='n2@example.com', role_code='N2', team_id=team, temporary_password='Temporary!Supervisor2026')
    created = mutate(client, '/access-requests', body)
    assert created.status_code == 201, created.text
    id = created.json()['data']['user_id']
    assert client.get('/api/v1/users/'+id).status_code == 200
    csrf = client.get('/api/v1/auth/csrf').json()['data']['csrf_token']
    response = client.patch('/api/v1/users/'+id, json={'name':"João D'Ávila"}, headers={'X-CSRF-Token':csrf,'Origin':'https://testserver'})
    assert response.status_code == 200, response.text
    assert client.get('/api/v1/users?search=João').json()['data']['total'] == 1
    assert mutate(client, '/users/'+id+'/activation/revalidate').status_code == 200
    assert mutate(client, '/users/'+id+'/recovery', {'mode':'BIOMETRIC','reason':'Teste'}).status_code == 409
    assert mutate(client, '/users/'+id+'/deactivate', {'reason':'Saiu da equipe'}).status_code == 200
    assert client.get('/api/v1/users?soft_delete=true').json()['data']['total'] == 1
    assert mutate(client, '/users/'+id+'/deactivate', {'reason':'Saiu'}).status_code == 409
    other = mutate(client, '/access-requests', dict(body, email='other@example.com'))
    assert other.status_code == 201, other.text
    assert mutate(client, '/users/'+id+'/reactivate', {'temporary_password':'Temporary!Restored2026','reason':'Retorno'}).status_code == 409
    assert mutate(client, '/users/'+other.json()['data']['user_id']+'/deactivate', {'reason':'Saiu'}).status_code == 200
    assert mutate(client, '/users/'+id+'/reactivate', {'temporary_password':'Temporary!Restored2026','reason':'Retorno'}).status_code == 200
    assert mutate(client, '/users/'+id+'/reactivate', {'temporary_password':'Temporary!Restored2026','reason':'Retorno'}).status_code == 409


def test_password_change_revokes_sessions_and_requires_current_password(client):
    """Troca voluntária exige senha atual, etapa correta e uma nova senha diferente.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    from conftest import mutate, FINAL_PASSWORD
    activate_admin(client)
    assert mutate(client, '/auth/password-change/start', {'current_password':'incorreta'}).status_code == 401
    started = mutate(client, '/auth/password-change/start', {'current_password':FINAL_PASSWORD})
    assert started.status_code == 200, started.text
    assert started.json()['data']['next_step'] == 'CHANGE_PASSWORD'
    assert client.get('/api/v1/auth/me').status_code == 200
    assert mutate(client, '/auth/password/complete', {'new_password':'Changed!Password2026', 'password_confirmation':'Changed!Password2026'}).status_code == 403
    assert mutate(client, '/auth/password-change/complete', {'new_password':FINAL_PASSWORD,'password_confirmation':FINAL_PASSWORD}).status_code == 422
    result = mutate(client, '/auth/password-change/complete', {'new_password':'Changed!Password2026','password_confirmation':'Changed!Password2026'})
    assert result.status_code == 200, result.text
    assert result.json()['data']['next_step'] == 'LOGIN'
    assert client.get('/api/v1/auth/me').status_code == 401
    assert mutate(client, '/auth/login', {'email':'admin@example.com','password':FINAL_PASSWORD}).status_code == 401
    assert mutate(client, '/auth/login', {'email':'admin@example.com','password':'Changed!Password2026'}).status_code == 200


import pytest


@pytest.mark.parametrize('mode',['PASSWORD','BIOMETRIC','BOTH'])
def test_recovery_and_preserved_activation(client,mode):
    """Recuperação revoga sessão e mantém a primeira ativação nos três modos.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        mode: Modo de recuperação parametrizado: PASSWORD, BIOMETRIC ou BOTH.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    from conftest import mutate, FINAL_PASSWORD
    from test_auth import frames
    activate_admin(client)
    team=client.get('/api/v1/teams').json()['data']['items'][0]['id']
    created=mutate(client,'/access-requests',dict(name='Ana',email='ana@example.com',role_code='N1',team_id=team,temporary_password='Temporary!Ana2026'))
    id=created.json()['data']['user_id']
    mutate(client,'/auth/logout')
    assert mutate(client,'/auth/login',dict(email='ana@example.com',password='Temporary!Ana2026')).status_code==200
    assert mutate(client,'/auth/biometric/enroll',files=frames()).status_code==200
    assert mutate(client,'/auth/password/complete',dict(new_password=FINAL_PASSWORD,password_confirmation=FINAL_PASSWORD)).status_code==200
    mutate(client,'/auth/logout')
    assert mutate(client,'/auth/login',dict(email='admin@example.com',password=FINAL_PASSWORD)).status_code==200
    before=client.get('/api/v1/users/'+id).json()['data']['activated_at']
    body={'mode':mode,'reason':'Recuperação autorizada'}
    if mode!='BIOMETRIC':
        body['temporary_password']='Recovery!Ana2026'
    result=mutate(client,'/users/'+id+'/recovery',body)
    assert result.status_code==200,result.text
    assert result.json()['data']['activated_at']==before
    mutate(client,'/auth/logout')
    password=FINAL_PASSWORD if mode=='BIOMETRIC' else 'Recovery!Ana2026'
    login=mutate(client,'/auth/login',dict(email='ana@example.com',password=password))
    assert login.status_code==200,login.text
    stage=login.json()['data']['next_step']
    assert stage==('VERIFY_FACE' if mode=='PASSWORD' else 'ENROLL_FACE')
    face=mutate(client,'/auth/biometric'+('/enroll' if stage=='ENROLL_FACE' else ''),files=frames())
    assert face.status_code==200,face.text
    if mode=='BIOMETRIC':
        assert face.json()['data']['next_step']=='SESSION'
    else:
        assert face.json()['data']['next_step']=='CHANGE_PASSWORD'
        assert mutate(client,'/auth/password/complete',dict(new_password='Restored!Ana2026',password_confirmation='Restored!Ana2026')).status_code==200


def test_development_seed_is_repeatable(client):
    """Carga manual não duplica contas nem redefine senha existente.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    from facial_recognition.seed.development import seed_development
    async def run():
        """Executa duas cargas sobre a mesma transação isolada do fixture.

        Returns:
            None: Operação concluída e verificações satisfeitas, quando presentes.
        """
        async with client.app.state.db_pool.acquire() as c:
            await seed_development(c)
            before=await c.fetchval("SELECT password_hash FROM password_hashes p JOIN users u ON u.id=p.user_id WHERE u.email='n1.a@example.com'")
            await seed_development(c)
            after=await c.fetchval("SELECT password_hash FROM password_hashes p JOIN users u ON u.id=p.user_id WHERE u.email='n1.a@example.com'")
            assert before==after
            assert await c.fetchval('SELECT count(*) FROM users')==7
            assert await c.fetchval('SELECT count(*) FROM validations')==1
    client.portal.call(run)


@pytest.mark.parametrize('simulated',[False,True])
def test_password_change_with_face(client,monkeypatch,simulated):
    """Prova facial avança para senha, sem criar sessão, nos dois caminhos HTTP.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        monkeypatch: Fixture pytest que substitui configuração/dependências e as restaura ao
            fim.
        simulated: Se True, usa a rota de simulação; False usa upload com inferência
            substituída.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    from conftest import mutate, FINAL_PASSWORD
    from test_auth_regressions import start_enrollment
    from test_auth import frames
    from facial_recognition.core.settings import settings
    if simulated:
        monkeypatch.setattr(settings,'BIOMETRICS_MODE','simulated')
    start_enrollment(client)
    face_path='/auth/biometric/simulate' if simulated else '/auth/biometric/enroll'
    assert mutate(client,face_path,files=None if simulated else frames()).status_code==200
    assert mutate(client,'/auth/password/complete',dict(new_password=FINAL_PASSWORD,password_confirmation=FINAL_PASSWORD)).status_code==200
    started=mutate(client,'/auth/password-change/start',{'current_password':FINAL_PASSWORD})
    assert started.status_code==200,started.text
    assert started.json()['data']['next_step']=='VERIFY_FACE'
    assert client.get('/api/v1/auth/flow').json()['data']['operation']=='PASSWORD_CHANGE'
    count=database_value(client,'SELECT count(*) FROM sessions')
    assert mutate(client,'/auth/password-change/complete',dict(new_password='Changed!Face2026',password_confirmation='Changed!Face2026')).status_code==403
    face=mutate(client,'/auth/biometric/simulate' if simulated else '/auth/biometric',files=None if simulated else frames())
    assert face.status_code==200,face.text
    assert face.json()['data']['next_step']=='CHANGE_PASSWORD'
    assert database_value(client,'SELECT count(*) FROM sessions')==count
    result=mutate(client,'/auth/password-change/complete',dict(new_password='Changed!Face2026',password_confirmation='Changed!Face2026'))
    assert result.status_code==200,result.text
    assert database_value(client,'SELECT count(*) FROM sessions WHERE revoked_at IS NULL')==0
    assert client.get('/api/v1/auth/me').status_code==401


@pytest.mark.parametrize('before_face',[True,False])
def test_revoked_initiating_session_blocks_password_change(client,monkeypatch,before_face):
    """Revogação da sessão iniciadora invalida prova facial e conclusão da senha.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        monkeypatch: Fixture pytest que substitui configuração/dependências e as restaura ao
            fim.
        before_face: Se True, revoga antes da prova facial; False revoga antes da conclusão da
            senha.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    from conftest import mutate, FINAL_PASSWORD
    from test_auth_regressions import start_enrollment
    from facial_recognition.core.settings import settings
    monkeypatch.setattr(settings,'BIOMETRICS_MODE','simulated')
    start_enrollment(client)
    assert mutate(client,'/auth/biometric/simulate').status_code==200
    assert mutate(client,'/auth/password/complete',dict(new_password=FINAL_PASSWORD,password_confirmation=FINAL_PASSWORD)).status_code==200
    assert mutate(client,'/auth/password-change/start',{'current_password':FINAL_PASSWORD}).status_code==200
    before=database_value(client,"SELECT password_hash FROM password_hashes p JOIN users u ON u.id=p.user_id WHERE u.email='review@example.com'")
    if not before_face:
        assert mutate(client,'/auth/biometric/simulate').json()['data']['next_step']=='CHANGE_PASSWORD'
    database_value(client,'UPDATE sessions SET revoked_at=NOW()')
    result=mutate(client,'/auth/biometric/simulate') if before_face else mutate(client,'/auth/password-change/complete',dict(new_password='Changed!Revoked2026',password_confirmation='Changed!Revoked2026'))
    assert result.status_code==401,result.text
    assert database_value(client,"SELECT password_hash FROM password_hashes p JOIN users u ON u.id=p.user_id WHERE u.email='review@example.com'")==before


def test_request_isolation_rejection_and_audit_sanitization(client):
    """Pedidos não atravessam solicitantes e auditoria omite conteúdo científico.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    from conftest import mutate
    from test_laboratory import login_as
    activate_admin(client)
    admin=client.get('/api/v1/auth/me').json()['data']['id']
    teams=client.get('/api/v1/teams').json()['data']['items']
    supervisors=[]
    for index,team in enumerate(teams):
        response=mutate(client,'/access-requests',dict(name='Supervisor',email=f'scope{index}@example.com',role_code='N2',team_id=team['id'],temporary_password='Temporary!Scope2026'))
        assert response.status_code==201,response.text
        supervisors.append(response.json()['data']['user_id'])
    database_value(client,"UPDATE users SET status='ACTIVE',activated_at=COALESCE(activated_at,NOW()),password_change_required=FALSE,biometric_enrollment_required=FALSE")
    login_as(client,supervisors[0])
    pending=mutate(client,'/access-requests',dict(name='Pedido',email='pending@example.com',temporary_password='Temporary!Pending2026')).json()['data']
    login_as(client,supervisors[1])
    assert client.get('/api/v1/access-requests').json()['data']['total']==0
    assert client.get('/api/v1/access-requests/'+pending['id']).status_code==404
    login_as(client,admin)
    from test_laboratory import patch
    assert patch(client,'/users/'+supervisors[0],{'email':'pending@example.com'}).status_code==409
    reason='Pedido sem justificativa institucional'
    rejected=mutate(client,'/access-requests/'+pending['id']+'/reject',{'reason':reason})
    assert rejected.status_code==200,rejected.text
    assert rejected.json()['data']['rejection_reason']==reason
    assert database_value(client,"SELECT count(*) FROM users WHERE email='pending@example.com'")==0
    assert database_value(client,"SELECT temporary_password_hash FROM access_requests WHERE requested_email='pending@example.com'") is None
    assert mutate(client,'/access-requests/'+pending['id']+'/approve').status_code==409
    database_value(client,"INSERT INTO audit_events(event,resource_type,reason,success,request_id) VALUES('PRIVATE','vault','Conteúdo científico reservado',TRUE,gen_random_uuid())")
    database_value(client,"INSERT INTO audit_events(event,resource_type,reason,soft_delete,success,request_id) VALUES('DELETED','users','Excluído',TRUE,TRUE,gen_random_uuid())")
    result=client.get('/api/v1/admin/audit-events?per_page=100')
    assert result.status_code==200,result.text
    assert 'Conteúdo científico reservado' not in result.text
    assert all(r['event'] not in {'PRIVATE','DELETED'} for r in result.json()['data']['items'])
    login_as(client,supervisors[0])
    assert client.get('/api/v1/access-requests/'+pending['id']).json()['data']['rejection_reason']==reason


@pytest.mark.parametrize('environment,mode',[('production','real'),('development','real'),('test','simulated')])
def test_development_seed_refuses_other_environments(monkeypatch,environment,mode):
    """CLI recusa ambiente/modo incompatível antes de abrir qualquer conexão.

    Args:
        monkeypatch: Fixture pytest que substitui configuração/dependências e as restaura ao
            fim.
        environment: Ambiente parametrizado para verificar as restrições de execução.
        mode: Modo de recuperação parametrizado: PASSWORD, BIOMETRIC ou BOTH.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    import asyncio
    from unittest.mock import AsyncMock
    from facial_recognition.seed import development
    pool=AsyncMock()
    monkeypatch.setattr(development.settings,'ENVIRONMENT',environment)
    monkeypatch.setattr(development.settings,'BIOMETRICS_MODE',mode)
    monkeypatch.setattr(development,'create_pool',pool)
    with pytest.raises(RuntimeError,match='development'):
        asyncio.run(development.main())
    pool.assert_not_awaited()


def test_development_seed_position_conflict_rolls_back(client):
    """Colisão de vaga no meio da carga não deixa contas fictícias parciais.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    from conftest import mutate
    from fastapi import HTTPException
    from facial_recognition.seed.development import seed_development
    activate_admin(client)
    team=str(database_value(client,"SELECT id FROM teams WHERE code='B'"))
    result=mutate(client,'/access-requests',dict(name='Supervisor existente',email='existing@example.com',role_code='N2',team_id=team,temporary_password='Temporary!Existing2026'))
    assert result.status_code==201,result.text
    async def run():
        """Reproduz a transação da CLI sem alterar schema public ou dados persistentes.

        Returns:
            None: Operação concluída e verificações satisfeitas, quando presentes.
        """
        async with client.app.state.db_pool.acquire() as c:
            before=await c.fetchval('SELECT count(*) FROM users')
            with pytest.raises(HTTPException) as error:
                async with c.transaction():
                    await seed_development(c)
            assert error.value.status_code==409
            assert await c.fetchval('SELECT count(*) FROM users')==before
            assert await c.fetchval('SELECT count(*) FROM biological_agents')==0
    client.portal.call(run)
