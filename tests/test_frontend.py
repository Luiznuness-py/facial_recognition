"""Smoke da entrega estática, sem banco, seed ou aprovação biométrica simulada."""
from fastapi.testclient import TestClient

from facial_recognition.app import app


def test_frontend_interaction_contracts():
    """Executa contratos JavaScript isolados de seleção, senha e filtros sem navegador.

    Node 18+ é uma ferramenta opcional de teste, não dependência da aplicação. O modelo
    DOM do teste verifica estados e eventos; não valida layout, motores ou leitor de tela.

    Returns:
        None: Todos os cenários JavaScript passam, ou o pytest registra skip sem Node 18+.

    Raises:
        AssertionError: Quando um cenário JavaScript falha.
        subprocess.TimeoutExpired: Quando a execução excede o limite de proteção do teste.
    """
    from pathlib import Path
    import shutil
    import subprocess
    import pytest
    node=shutil.which('node')
    if not node:
        pytest.skip('Contratos JavaScript requerem Node 18+; a aplicação não depende de Node.')
    version=subprocess.run([node,'--version'],capture_output=True,text=True,check=True)
    if int(version.stdout.lstrip('v').split('.')[0])<18:
        pytest.skip('Contratos JavaScript requerem Node 18+.')
    script=Path(__file__).with_name('frontend_ui.test.mjs')
    result=subprocess.run([node,str(script)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr


def test_responsive_photographs_and_credits():
    """Confere entrega, dimensões, tamanhos e créditos dos recursos WebP locais.

    As respostas usam TestClient sem lifespan; não inicializam banco nem inferência.
    Integridade e proporção não comprovam composição visual em navegadores reais.

    Returns:
        None: Todas as variantes são entregues com proporção correta e crédito presente.

    Raises:
        AssertionError: Para arquivo ausente, dimensão/tamanho incorretos ou crédito ausente.
    """
    from io import BytesIO
    from PIL import Image
    from pathlib import Path
    client=TestClient(app)
    heights={'amazonia':786,'anavilhanas':859,'mata-atlantica':960,'tucano':753}
    for name,height in heights.items():
        for width in (640,1280):
            response=client.get(f'/static/assets/{name}-{width}.webp')
            assert response.status_code==200
            assert response.headers['content-type']=='image/webp'
            photo=Image.open(BytesIO(response.content))
            assert photo.width==width
            assert abs(photo.height-height*width/1280)<=1
            assert len(response.content)<250_000
    assert client.get('/static/photos.js').status_code==200
    credits=(Path(__file__).resolve().parents[1]/'facial_recognition/frontend/static/assets/CREDITS.md').read_text()
    for name in ('lubasi','Jason Auch','Naná Voitille','AntanO'):
        assert name in credits


def test_documented_operations_are_registered():
    """Confere métodos e caminhos de todos os contratos publicados no OpenAPI.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    import re
    from pathlib import Path
    document=(Path(__file__).resolve().parents[1]/'docs/ENDPOINTS.md').read_text()
    operations=set(re.findall(r'`(GET|POST|PATCH|DELETE) (/[\w/{}/-]+)`',document))
    paths={path.rstrip('/'):value for path,value in app.openapi()['paths'].items()}
    assert len(operations)>=58
    missing=[]
    for method,path in operations:
        target=path if path=='/health' else '/api/v1'+path
        if method.lower() not in paths.get(target,{}):
            missing.append((method,target))
    assert not missing,missing


def test_frontend_assets_and_security_headers():
    # Sem entrar no contexto, TestClient não executa o lifespan nem conecta ao banco.
    """Confere HTML, módulos, logos e cabeçalhos sem inicializar banco ou modelos.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
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
