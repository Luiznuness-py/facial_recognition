"""Regressões dos problemas encontrados na revisão da bancada."""
import numpy as np
import pytest

from conftest import ADMIN_PASSWORD, FINAL_PASSWORD, activate_admin, mutate
from facial_recognition.exceptions.biometrics import BiometricError
from test_auth import frames


def database_value(client, statement, *values):
    """Executa uma consulta escalar na conexão transacional do fixture.

    Args:
        client: TestClient cujo portal executa a coroutine no loop correto.
        statement: SQL controlado pelo teste, sem interpolar valores externos.
        values: Valores encaminhados como parâmetros separados ao asyncpg.

    Returns:
        Any: Primeira coluna da primeira linha, ou None quando não existe resultado.
    """
    async def query():
        """Encaminha a consulta escalar à conexão compartilhada do caso.

        Returns:
            Any: Resultado de fetchval, capturando SQL e parâmetros do auxiliar externo.
        """
        async with client.app.state.db_pool.acquire() as connection:
            return await connection.fetchval(statement, *values)
    return client.portal.call(query)


def start_enrollment(client):
    """Prepara um ADMIN, cria N1 e inicia a etapa de cadastro facial.

    Args:
        client: Cliente HTTP do fixture com inferência substituída por padrão.

    Returns:
        None: Deixa o cliente com o cookie restrito ENROLL_FACE da conta fictícia.

    Raises:
        AssertionError: Quando criação, logout ou login não produzem os estados esperados.
    """
    activate_admin(client)
    team = client.get('/api/v1/teams').json()['data']['items'][0]['id']
    body = {
        'name': 'Revisão',
        'email': 'review@example.com',
        'role_code': 'N1',
        'team_id': team,
        'temporary_password': 'Temporary!Review2026',
    }
    response = mutate(client, '/access-requests', body)
    assert response.status_code == 201, response.text
    assert mutate(client, '/auth/logout').status_code == 204
    response = mutate(client, '/auth/login', {
        'email': body['email'], 'password': body['temporary_password'],
    })
    assert response.status_code == 200, response.text
    assert response.json()['data']['next_step'] == 'ENROLL_FACE'


def test_deleted_password_blocks_pending_activation(client):
    """Confere que excluir a senha impede concluir a ativação e não altera hash, status ou
    sessões.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    assert mutate(client, '/auth/login', {
        'email': 'admin@example.com', 'password': ADMIN_PASSWORD,
    }).status_code == 200
    original_hash = database_value(client, 'SELECT password_hash FROM password_hashes')
    database_value(client, 'UPDATE password_hashes SET soft_delete=TRUE')

    assert client.get('/api/v1/auth/flow').status_code == 401
    response = mutate(client, '/auth/password/complete', {
        'new_password': FINAL_PASSWORD, 'password_confirmation': FINAL_PASSWORD,
    })
    assert response.status_code == 401
    assert database_value(client, 'SELECT password_hash FROM password_hashes') == original_hash
    assert database_value(client, 'SELECT status FROM users') == 'PENDING_ACTIVATION'
    assert database_value(client, 'SELECT count(*) FROM sessions') == 0


@pytest.mark.parametrize('deleted_record', ['password', 'attempt'])
@pytest.mark.parametrize('rejected', [False, True])
def test_deletion_during_inference_prevents_writes(client, deleted_record, rejected):
    """Confere que uma exclusão durante a inferência impede gravar resultado ou contadores.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.
        deleted_record: Registro a excluir durante a inferência: password ou attempt.
        rejected: Indica se o stub deve reprovar a biometria em vez de devolver um template.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    start_enrollment(client)

    async def inference(contents, reference):
        # Simula a exclusão depois da validação inicial e antes da gravação.
        """Exclui a senha ou tentativa depois da validação inicial da rota.

        Usa a conexão do fixture para reproduzir uma alteração de estado antes da gravação
        do resultado. Não é uma medição de concorrência entre processos reais.

        Args:
            contents: Arquivos ignorados pelo stub.
            reference: Template ignorado pelo stub.

        Returns:
            numpy.ndarray: Vetor normalizado quando o cenário simula aprovação.

        Raises:
            BiometricError: Categoria rejected quando o cenário simula reprovação.
        """
        async with client.app.state.db_pool.acquire() as connection:
            user_id = await connection.fetchval("SELECT id FROM users WHERE email='review@example.com'")
            if deleted_record == 'password':
                await connection.execute('UPDATE password_hashes SET soft_delete=TRUE WHERE user_id=$1', user_id)
            else:
                await connection.execute('UPDATE authentication_attempts SET soft_delete=TRUE WHERE user_id=$1', user_id)
        if rejected:
            raise BiometricError('PAD reprovado', 'rejected')
        return np.ones(128, dtype=np.float32) / np.sqrt(128)

    client.app.state.inference = inference
    response = mutate(client, '/auth/biometric/enroll', files=frames())
    assert response.status_code == 401
    assert database_value(client, 'SELECT count(*) FROM vectors') == 0
    assert database_value(client, "SELECT biometric_enrollment_required FROM users WHERE email='review@example.com'")
    assert database_value(client, "SELECT biometric_failure_count FROM users WHERE email='review@example.com'") == 0
    assert database_value(client, "SELECT count(*) FROM audit_events WHERE event IN('FACE_ENROLLED','BIOMETRIC_REJECTED')") == 0


def test_user_creation_audit_identifies_user_resource(client):
    """Confere autor, recurso users e UUID da conta no evento de criação.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    start_enrollment(client)
    user_id = database_value(client, "SELECT id FROM users WHERE email='review@example.com'")
    assert database_value(client, "SELECT resource_type FROM audit_events WHERE event='USER_CREATED'") == 'users'
    assert database_value(client, "SELECT resource_id FROM audit_events WHERE event='USER_CREATED'") == user_id
    assert database_value(client, "SELECT actor_id FROM audit_events WHERE event='USER_CREATED'") == database_value(client, "SELECT id FROM users WHERE email='admin@example.com'")


@pytest.mark.parametrize('context', ['session', 'stage', 'refresh_only', 'anonymous'])
def test_logout_audits_identified_context_once(client, context):
    """Confere auditoria e revogação do logout por sessão, etapa, refresh ou contexto anônimo.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.
        context: Contexto de logout a testar: session, stage, refresh_only ou anonymous.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    if context in {'session', 'refresh_only'}:
        activate_admin(client)
    elif context == 'stage':
        assert mutate(client, '/auth/login', {
            'email': 'admin@example.com', 'password': ADMIN_PASSWORD,
        }).status_code == 200
    if context == 'refresh_only':
        client.cookies.delete('lab_access', domain='testserver.local', path='/api/v1')

    response = mutate(client, '/auth/logout')
    assert response.status_code == 204
    expected_count = 0 if context == 'anonymous' else 1
    assert database_value(client, "SELECT count(*) FROM audit_events WHERE event='LOGOUT'") == expected_count
    assert not any(name in client.cookies for name in ['lab_access', 'lab_stage', 'lab_refresh'])
    if context != 'anonymous':
        resource_type = 'authentication_attempts' if context == 'stage' else 'sessions'
        assert database_value(client, "SELECT resource_type FROM audit_events WHERE event='LOGOUT'") == resource_type
        assert database_value(client, "SELECT actor_id FROM audit_events WHERE event='LOGOUT'") == database_value(client, 'SELECT id FROM users')
        if context == 'stage':
            assert database_value(client, 'SELECT status FROM authentication_attempts') == 'CANCELLED'
            assert database_value(client, "SELECT resource_id FROM audit_events WHERE event='LOGOUT'") == database_value(client, 'SELECT id FROM authentication_attempts')
        else:
            assert database_value(client, 'SELECT revoked_at FROM sessions') is not None
            assert database_value(client, "SELECT resource_id FROM audit_events WHERE event='LOGOUT'") == database_value(client, 'SELECT id FROM sessions')


@pytest.mark.parametrize('content_type', [
    'multipart/form-data; boundary=review',
    'multipart/form-data',
    'application/json',
    None,
])
def test_invalid_multipart_returns_validation_error(client, content_type):
    """Confere erro 422 para multipart malformado sem template ou falha biométrica gravados.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.
        content_type: Cabeçalho de upload inválido, ou None para testar a ausência.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    start_enrollment(client)
    csrf = client.get('/api/v1/auth/csrf').json()['data']['csrf_token']
    headers = {'Origin': 'https://testserver', 'X-CSRF-Token': csrf}
    if content_type is not None:
        headers['Content-Type'] = content_type
    response = client.post('/api/v1/auth/biometric/enroll', content=b'garbage', headers=headers)
    assert response.status_code == 422
    assert response.json()['success'] is False
    assert 'MultipartParseError' not in response.text
    assert database_value(client, 'SELECT count(*) FROM vectors') == 0
    assert database_value(client, "SELECT biometric_failure_count FROM users WHERE email='review@example.com'") == 0
def test_password_comparisons_run_outside_event_loop(client,monkeypatch):
    """Ativação e troca verificam Argon2 em thread, inclusive ao recusar a mesma senha.

    Args:
        client: TestClient HTTPS do fixture, com PostgreSQL transacional e inferência
            substituída.
        monkeypatch: Fixture pytest que substitui configuração/dependências e as restaura ao
            fim.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    import asyncio
    from conftest import ADMIN_PASSWORD, FINAL_PASSWORD, mutate
    from facial_recognition.routers import auth
    original=auth.check_password
    calls=[]
    def compare(password,encoded):
        """Registra se a thread tem loop em execução e delega a comparação ao Argon2 real, sem substituir seu resultado..

        Args:
            password: Senha fictícia candidata cuja comparação será observada pelo teste.
            encoded: Hash Argon2 atual da credencial fictícia usada no teste.

        Returns:
            bool: Resultado real da verificação da senha fictícia.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            calls.append('thread')
        else:
            calls.append('loop')
        return original(password,encoded)
    assert mutate(client,'/auth/login',dict(email='admin@example.com',password=ADMIN_PASSWORD)).status_code==200
    monkeypatch.setattr(auth,'check_password',compare)
    for password,status in ((ADMIN_PASSWORD,422),(FINAL_PASSWORD,200)):
        assert mutate(client,'/auth/password/complete',dict(new_password=password,password_confirmation=password)).status_code==status
    assert calls==['thread','thread'],calls
    assert mutate(client,'/auth/password-change/start',dict(current_password=FINAL_PASSWORD)).status_code==200
    calls.clear()
    for password,status in ((FINAL_PASSWORD,422),('Changed!Thread2026',200)):
        assert mutate(client,'/auth/password-change/complete',dict(new_password=password,password_confirmation=password)).status_code==status
    assert calls==['thread','thread'],calls
