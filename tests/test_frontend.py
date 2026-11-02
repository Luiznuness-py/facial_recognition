"""Smoke da entrega estática, sem banco, seed ou aprovação biométrica simulada."""
from fastapi.testclient import TestClient

from facial_recognition.app import app


def test_frontend_assets_and_security_headers():
    # Sem entrar no contexto, TestClient não executa o lifespan nem conecta ao banco.
    """Confere HTML, módulos, logos e cabeçalhos sem inicializar banco ou modelos."""
    client = TestClient(app, base_url="https://testserver")
    response = client.get("/lab")
    assert response.status_code == 200
    assert 'lang="pt-BR"' in response.text
    assert 'type="module"' in response.text
    assert 'href="#content"' in response.text
    assert 'frame-ancestors' in response.headers['content-security-policy']
    for filename in ("lab.js", "api.js", "ui.js", "auth.js", "admin.js", "science.js", "public.js", "lab.css"):
        asset = client.get("/static/" + filename)
        assert asset.status_code == 200, filename
    for filename in ("logo-com-texto.png", "logo-simbolo.png"):
        asset = client.get("/static/assets/" + filename)
        assert asset.status_code == 200
        assert asset.headers["content-type"] == "image/png"
    assert 'gov.br/icmbio' in response.text
    assert 'gov.br/mma' in response.text
