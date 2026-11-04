"""Correlação HTTP/auditoria sem acessar banco ou carregar modelos."""
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from facial_recognition.app import response_headers
from facial_recognition.exceptions.handlers import (
    http_error, validation_error, unexpected_error,
)
from facial_recognition.core.request_limit import RequestLimits
from facial_recognition.utils.utils import audit


@pytest.fixture
def tracked_client():
    """Prepara HTTP e auditoria simulada, sem banco ou modelos reais."""
    app = FastAPI()
    app.add_middleware(RequestLimits)
    app.middleware('http')(response_headers)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, unexpected_error)
    connection = AsyncMock()

    @app.get('/api/v1/events')
    async def events(request: Request):
        """Emite dois eventos na conexão simulada para conferir correlação."""
        for event in ['FACE_VERIFIED', 'SESSION_CREATED']:
            await audit(connection, None, event, 'sessions',
                        request_id=request.state.request_id)
        return {'ok': True}

    @app.post('/api/v1/input')
    async def input_data(value: int):
        """Expõe um parâmetro tipado para provocar erro de validação HTTP."""
        return {'value': value}

    @app.get('/api/v1/denied')
    async def denied():
        """Produz uma recusa HTTP controlada para testar seu envelope."""
        raise HTTPException(403, 'Acesso negado')

    @app.get('/api/v1/broken')
    async def broken():
        """Provoca falha inesperada para conferir sanitização e correlação."""
        raise RuntimeError('secret must not escape')

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, connection


def test_audit_shares_server_generated_request_id(tracked_client):
    """Confere o mesmo UUID por chamada e ignora o valor enviado pelo cliente."""
    client, connection = tracked_client
    first = client.get('/api/v1/events', headers={'X-Request-ID': 'client-value'})
    second = client.get('/api/v1/events')
    first_id = UUID(first.headers['X-Request-ID'])
    second_id = UUID(second.headers['X-Request-ID'])
    assert first.status_code == second.status_code == 200
    assert first_id != second_id
    assert [call.args[-1] for call in connection.execute.await_args_list] == [
        first_id, first_id, second_id, second_id,
    ]


@pytest.mark.parametrize('path,status', [
    ('/api/v1/denied', 403), ('/api/v1/missing', 404),
    ('/api/v1/broken', 500),
])
def test_errors_include_same_id_and_internal_log(tracked_client, caplog, path, status):
    """Relaciona cabeçalho, erro e log pelo mesmo UUID sem expor detalhes internos."""
    client, _ = tracked_client
    response = client.get(path)
    assert response.status_code == status
    request_id = response.headers['X-Request-ID']
    UUID(request_id)
    assert response.json()['error']['details']['request_id'] == request_id
    assert 'secret must not escape' not in response.text
    if status == 500:
        assert request_id in caplog.text


def test_validation_and_body_limit_include_request_id(tracked_client):
    """Confere identificação de erros do parser e do limite de corpo."""
    client, _ = tracked_client
    for body, status in [(b'', 422), (b'x' * (256 * 1024 + 1), 413)]:
        response = client.post('/api/v1/input', content=body)
        assert response.status_code == status
        assert response.json()['error']['details']['request_id'] == response.headers['X-Request-ID']


def test_rate_limit_includes_request_id_and_retry_after(tracked_client):
    """Preserva correlação e orientação de nova tentativa no bloqueio de frequência."""
    client, _ = tracked_client
    for _ in range(121):
        response = client.get('/api/v1/missing')
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '60'
    assert response.json()['error']['details']['request_id'] == response.headers['X-Request-ID']


def test_real_app_registers_context_before_limits():
    """Verifica a ordem real dos middlewares sem executar o lifespan."""
    from facial_recognition.app import app
    # Sem contexto de lifespan: não abre banco nem executa o reset de test.
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/health')
    assert response.status_code == 200
    UUID(response.headers['X-Request-ID'])
    response = client.post('/api/v1/auth/login', content=b'x' * (256 * 1024 + 1))
    assert response.status_code == 413
    assert response.json()['error']['details']['request_id'] == response.headers['X-Request-ID']


def test_concurrent_requests_keep_separate_ids(tracked_client):
    """Impede mistura de identificadores entre chamadas simultâneas."""
    import asyncio
    import httpx
    client, connection = tracked_client

    async def scenario():
        """Executa o cenário assíncrono isolado e devolve seus resultados."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url='http://testserver',
        ) as async_client:
            return await asyncio.gather(*[
                async_client.get('/api/v1/events') for _ in range(5)
            ])

    responses = asyncio.run(scenario())
    ids = [UUID(response.headers['X-Request-ID']) for response in responses]
    assert len(set(ids)) == 5
    recorded = [call.args[-1] for call in connection.execute.await_args_list]
    assert len(recorded) == 10
    assert all(recorded.count(request_id) == 2 for request_id in ids)
