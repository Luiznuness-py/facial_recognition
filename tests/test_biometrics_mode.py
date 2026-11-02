"""Modo explícito e simulação sem imagens, banco ou câmera reais."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from facial_recognition.core.settings import Settings, settings
from facial_recognition.core.security import token_hash
from facial_recognition.core.token_jwt import TokenJwt
from facial_recognition.routers.auth import authentication, simulate_biometric
from facial_recognition.utils.utils import now


def test_mode_is_required(monkeypatch):
    """Rejeita configuração sem escolha explícita do modo biométrico."""
    monkeypatch.delenv('BIOMETRICS_MODE', raising=False)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, ADMIN_SECRET='dummy', SECRET_KEY='x' * 32)
    assert any(e['loc'] == ('BIOMETRICS_MODE',) and e['type'] == 'missing' for e in error.value.errors())


@pytest.mark.parametrize('environment,mode,valid', [
    ('development', 'simulated', True), ('test', 'simulated', True),
    ('production', 'simulated', False), ('other', 'simulated', False),
    ('production', 'real', True), ('development', 'invalid', False),
])
def test_mode_configuration(environment, mode, valid):
    """Restringe simulação a development/test e recusa valores desconhecidos."""
    args = dict(_env_file=None, ENVIRONMENT=environment, BIOMETRICS_MODE=mode,
                ADMIN_SECRET='dummy', SECRET_KEY='x' * 32)
    if valid:
        assert Settings(**args).BIOMETRICS_MODE == mode
    else:
        with pytest.raises(ValidationError):
            Settings(**args)


def test_simulated_credentials_do_not_validate_in_real_mode(monkeypatch):
    """Impede reutilizar JWT ou refresh de simulação no modo real."""
    tokens = TokenJwt('x' * 32)
    monkeypatch.setattr(settings, 'BIOMETRICS_MODE', 'simulated')
    token = tokens.create_token(uuid4(), 'ACCESS', 900, session_id=str(uuid4()))
    simulated_hash = token_hash('opaque-refresh')
    monkeypatch.setattr(settings, 'BIOMETRICS_MODE', 'real')
    assert token_hash('opaque-refresh') != simulated_hash
    with pytest.raises(HTTPException):
        tokens.validate_token(token, 'ACCESS')


@pytest.mark.parametrize('stage,password_change', [('ENROLL_FACE', True), ('VERIFY_FACE', False)])
def test_simulation_transitions_without_vectors(monkeypatch, stage, password_change):
    """Confere a etapa seguinte e auditoria sem gravar vetores fictícios."""
    monkeypatch.setattr(settings, 'BIOMETRICS_MODE', 'simulated')
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'development')
    connection = MagicMock()
    connection.execute = AsyncMock()
    request = SimpleNamespace(state=SimpleNamespace(request_id=uuid4()), body=AsyncMock(return_value=b''))
    attempt = dict(id=uuid4(), stage=stage, operation='ACTIVATION' if password_change else 'LOGIN')
    user = dict(id=uuid4(), is_temporary=password_change, temporary_expires_at=now()+timedelta(hours=1),
                biometric_enrollment_required=stage == 'ENROLL_FACE', password_change_required=password_change)
    monkeypatch.setattr(authentication, 'lock_attempt', AsyncMock(return_value=user))
    monkeypatch.setattr(authentication, 'issue_stage', AsyncMock(return_value={'next_step': 'CHANGE_PASSWORD', 'expires_in': 300}))
    monkeypatch.setattr(authentication, 'issue_session', AsyncMock(return_value={'next_step': 'SESSION'}))
    result = asyncio.run(simulate_biometric(request, Response(), connection, attempt))
    assert result.data['next_step'] == ('CHANGE_PASSWORD' if password_change else 'SESSION')
    assert not any('vectors' in call.args[0] for call in connection.execute.await_args_list)
    assert any('BIOMETRIC_SIMULATED' in call.args for call in connection.execute.await_args_list)
    authentication.lock_attempt.assert_awaited_once()


@pytest.mark.parametrize('mode,environment,stage,body,status', [
    ('real', 'development', 'VERIFY_FACE', b'', 403),
    ('simulated', 'production', 'VERIFY_FACE', b'', 403),
    ('simulated', 'test', 'CHANGE_PASSWORD', b'', 403),
    ('simulated', 'test', 'VERIFY_FACE', b'{}', 422),
])
def test_simulation_rejects_forbidden_calls(monkeypatch, mode, environment, stage, body, status):
    """Recusa modo, ambiente, etapa ou corpo incompatíveis antes da transação."""
    monkeypatch.setattr(settings, 'BIOMETRICS_MODE', mode)
    monkeypatch.setattr(settings, 'ENVIRONMENT', environment)
    request = SimpleNamespace(body=AsyncMock(return_value=body))
    connection = MagicMock()
    with pytest.raises(HTTPException) as error:
        asyncio.run(simulate_biometric(request, Response(), connection,
                                      dict(stage=stage, operation='LOGIN')))
    assert error.value.status_code == status
    connection.transaction.assert_not_called()


def test_simulated_startup_does_not_load_models(monkeypatch):
    """Inicializa recursos simulados sem carregar pesos e garante fechamento do pool."""
    import facial_recognition.app as application
    monkeypatch.setattr(settings, 'BIOMETRICS_MODE', 'simulated')
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'test')
    load = MagicMock(side_effect=AssertionError('Não carregar modelos na simulação'))
    monkeypatch.setattr(application.FaceModels, 'load', load)
    pool = MagicMock()
    pool.close = AsyncMock()
    monkeypatch.setattr(application, 'create_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(application, 'run_migrations', AsyncMock())
    monkeypatch.setattr(application, 'run_seeds', AsyncMock())
    monkeypatch.setattr(application, 'drop_all_tables', AsyncMock())

    async def scenario():
        """Executa o cenário assíncrono isolado e devolve seus resultados."""
        async with application.lifespan(application.app):
            assert application.app.state.inference is None
    asyncio.run(scenario())
    load.assert_not_called()
    pool.close.assert_awaited_once()


def test_simulated_account_flow_with_database(client, monkeypatch):
    """Percorre ativação/login simulado reais no banco e recusa credenciais no modo real."""
    from conftest import activate_admin, mutate, FINAL_PASSWORD
    monkeypatch.setattr(settings, 'BIOMETRICS_MODE', 'simulated')
    activate_admin(client)
    team = client.get('/api/v1/teams').json()['data']['items'][0]['id']
    account = dict(name='Pessoa simulada', email='simulated@example.com', role_code='N1',
                   team_id=team, temporary_password='Temporary!Simulated2026')
    assert mutate(client, '/access-requests', account).status_code == 201
    assert mutate(client, '/auth/logout').status_code == 204
    assert mutate(client, '/auth/biometric/simulate').status_code == 401
    credentials = dict(email=account['email'], password=account['temporary_password'])
    assert mutate(client, '/auth/login', credentials).json()['data']['next_step'] == 'ENROLL_FACE'
    assert client.get('/api/v1/auth/flow').json()['data']['biometrics_mode'] == 'simulated'
    assert mutate(client, '/auth/biometric/simulate').json()['data']['next_step'] == 'CHANGE_PASSWORD'
    assert mutate(client, '/auth/biometric/simulate').status_code == 403
    assert mutate(client, '/auth/password/complete', dict(
        new_password=FINAL_PASSWORD, password_confirmation=FINAL_PASSWORD,
    )).status_code == 200
    assert client.get('/api/v1/auth/me').json()['data']['role'] == 'N1'
    assert mutate(client, '/access-requests', account).status_code == 403

    async def check_database():
        """Confere ausência de vetor e presença do evento explícito da simulação."""
        async with client.app.state.db_pool.acquire() as connection:
            assert await connection.fetchval('SELECT count(*) FROM vectors') == 0
            assert await connection.fetchval(
                "SELECT count(*) FROM audit_events WHERE event='BIOMETRIC_SIMULATED'",
            ) == 1
    client.portal.call(check_database)
    assert mutate(client, '/auth/logout').status_code == 204
    credentials['password'] = FINAL_PASSWORD
    assert mutate(client, '/auth/login', credentials).json()['data']['next_step'] == 'VERIFY_FACE'
    assert mutate(client, '/auth/biometric/simulate').json()['data']['next_step'] == 'SESSION'
    monkeypatch.setattr(settings, 'BIOMETRICS_MODE', 'real')
    assert client.get('/api/v1/auth/me').status_code == 401
    assert mutate(client, '/auth/refresh').status_code == 401
