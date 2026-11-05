"""Política de transporte dos cookies sem banco ou servidor de rede."""
from http.cookies import SimpleCookie

import pytest
from fastapi import HTTPException, Request, Response

from facial_recognition.core.security import set_cookie
from facial_recognition.core.settings import settings


@pytest.mark.parametrize('environment', ['development', 'test', 'production', 'unknown'])
@pytest.mark.parametrize('scheme', ['http', 'https'])
@pytest.mark.parametrize('host', ['localhost', '127.0.0.1', '[::1]', '192.168.1.50', 'testserver'])
def test_cookie_transport(monkeypatch, environment, scheme, host):
    """Valida transporte permitido e atributos dos quatro cookies por ambiente.

    Args:
        monkeypatch: Fixture pytest que substitui configuração/dependências e as restaura ao
            fim.
        environment: Ambiente parametrizado para verificar as restrições de execução.
        scheme: Esquema HTTP ou HTTPS usado para verificar o transporte dos cookies.
        host: Hostname parametrizado para verificar as restrições de loopback.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    monkeypatch.setattr(settings, 'ENVIRONMENT', environment)
    request = Request({
        'type': 'http', 'scheme': scheme, 'path': '/', 'root_path': '',
        'query_string': b'', 'headers': [(b'host', host.encode())],
        'server': ('localhost', 8000),
    })
    response = Response()
    allowed = scheme == 'https' or (
        environment in {'development', 'test'}
        and host in {'localhost', '127.0.0.1', '[::1]'}
    )
    if not allowed:
        with pytest.raises(HTTPException) as error:
            set_cookie(response, request, 'lab_access', 'dummy', 900)
        assert error.value.status_code == 400
        assert 'set-cookie' not in response.headers
        return
    for name, path in [('lab_access', '/api/v1'), ('lab_csrf_context', '/api/v1'),
                       ('lab_stage', '/api/v1/auth'), ('lab_refresh', '/api/v1/auth')]:
        response = Response()
        set_cookie(response, request, name, 'dummy', 900)
        cookie = SimpleCookie(response.headers['set-cookie'])[name]
        assert bool(cookie['secure']) == (scheme == 'https')
        assert cookie['httponly']
        assert cookie['samesite'] == 'strict'
        assert cookie['path'] == path
        assert cookie['max-age'] == '900'
        assert not cookie['domain']
