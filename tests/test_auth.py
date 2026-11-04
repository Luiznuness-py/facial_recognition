import io
from uuid import uuid4

import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image

from facial_recognition.core.token_jwt import TokenJwt
from facial_recognition.core.security import encrypt_vector,decrypt_vector
from facial_recognition.core.biometrics import decode_frame
from facial_recognition.exceptions.biometrics import BiometricError
from conftest import mutate,activate_admin,FINAL_PASSWORD


def frames():
    """Cria cinco arquivos JPEG sintéticos para os testes de fluxo.

    As imagens não possuem rosto e são usadas com o stub de inferência; não simulam
    aprovação dos pesos reais.

    Returns:
        list[tuple]: Partes multipart chamadas frames com imagens RGB de 100 × 100.
    """
    stream=io.BytesIO();Image.new('RGB',(100,100)).save(stream,'JPEG')
    return [('frames',('image.jpg',stream.getvalue(),'image/jpeg')) for _ in range(5)]


def test_jwt_purposes_expiry_and_required_fields():
    """Confere finalidade, expiração e claims obrigatórios dos JWTs.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    tokens=TokenJwt('x'*32);user=uuid4()
    access=tokens.create_token(user,'ACCESS',900,session_id=str(uuid4()))
    assert tokens.validate_token(access,'ACCESS')['sub']==str(user)
    for token,kind in [(access,'RESTRICTED'),(tokens.create_token(user,'ACCESS',-1,session_id=str(uuid4())),'ACCESS'),(tokens.create_token(user,'ACCESS',30),'ACCESS'),('invalid','ACCESS')]:
        with pytest.raises(HTTPException) as error:tokens.validate_token(token,kind)
        assert error.value.status_code==401


def test_encryption_is_bound_to_user():
    """Confere a recuperação dos bytes e a recusa do mesmo vetor para outra conta.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    tokens=TokenJwt('a'*32);user=uuid4()
    encrypted,nonce=encrypt_vector(tokens,user,b'private-vector')
    assert b'private-vector' not in encrypted
    assert decrypt_vector(tokens,user,encrypted,nonce)==b'private-vector'
    from cryptography.exceptions import InvalidTag
    with pytest.raises(InvalidTag):decrypt_vector(tokens,uuid4(),encrypted,nonce)


def test_frame_validation():
    """Confere decodificação válida e rejeição de bytes, tamanho e dimensões inválidas.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    assert decode_frame(frames()[0][1][1]).shape==(100,100,3)
    for value in [b'invalid',b'a'*(1024*1024+1)]:
        with pytest.raises(BiometricError):decode_frame(value)
    buffer=io.BytesIO();Image.new('RGB',(1921,20)).save(buffer,'PNG')
    with pytest.raises(BiometricError):decode_frame(buffer.getvalue())


def test_admin_first_access_and_revocation(client):
    """Confere a ativação do ADMIN e a recusa do access após logout.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    assert client.get('/api/v1/teams').status_code==401
    activate_admin(client)
    assert client.get('/api/v1/auth/me').json()['data']['role']=='ADMIN'
    cookie=client.cookies.get('lab_access')
    assert 'HttpOnly' in mutate(client,'/auth/refresh').headers.get('set-cookie','')
    assert mutate(client,'/auth/logout').status_code==204
    client.cookies.set('lab_access',cookie,path='/api/v1')
    assert client.get('/api/v1/auth/me').status_code==401


def test_csrf_wrong_origin_and_missing_protection(client):
    """Confere a recusa de CSRF ausente e de chamadas com origem diferente.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    assert client.post('/api/v1/auth/login',json={}).status_code==403
    token=client.get('/api/v1/auth/csrf').json()['data']['csrf_token']
    response=client.post('/api/v1/auth/login',json={},headers={'Origin':'https://evil.example','X-CSRF-Token':token})
    assert response.status_code==403
    assert client.get('/api/v1/auth/csrf',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403


def test_complete_user_enrollment_login_and_permissions(client):
    """Exercita cadastro, ativação e login N1 sem permitir usar etapa como access ou acessar
    contas administrativas.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    activate_admin(client)
    team=client.get('/api/v1/teams').json()['data']['items'][0]['id']
    body=dict(name='Ana',email='ana@example.com',role_code='N1',team_id=team,temporary_password='Temporary!Ana2026')
    created=mutate(client,'/access-requests',body)
    assert created.status_code==201,created.text
    assert 'Temporary!Ana2026' not in created.text
    assert mutate(client,'/access-requests',body).status_code==409
    mutate(client,'/auth/logout')
    response=mutate(client,'/auth/login',{'email':body['email'],'password':body['temporary_password']})
    assert response.json()['data']['next_step']=='ENROLL_FACE'
    stage=client.cookies.get('lab_stage')
    client.cookies.set('lab_access',stage,path='/api/v1')
    assert client.get('/api/v1/teams').status_code==401
    client.cookies.delete('lab_access',path='/api/v1')
    assert mutate(client,'/auth/biometric',files=frames()).status_code==403
    response=mutate(client,'/auth/biometric/enroll',files=frames())
    assert response.status_code==200,response.text
    assert response.json()['data']['next_step']=='CHANGE_PASSWORD'
    assert mutate(client,'/auth/biometric/enroll',files=frames()).status_code==403
    response=mutate(client,'/auth/password/complete',{'new_password':FINAL_PASSWORD,'password_confirmation':FINAL_PASSWORD})
    assert response.status_code==200,response.text
    assert client.get('/api/v1/users').status_code==403
    assert client.get('/api/v1/teams').status_code==200
    mutate(client,'/auth/logout')
    assert mutate(client,'/auth/login',{'email':body['email'],'password':FINAL_PASSWORD}).json()['data']['next_step']=='VERIFY_FACE'
    assert mutate(client,'/auth/biometric',files=frames()).json()['data']['next_step']=='SESSION'


def test_refresh_replay_revokes_session(client):
    """Confere que reutilizar um refresh consumido revoga a sessão.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    activate_admin(client)
    old=client.cookies.get('lab_refresh')
    assert mutate(client,'/auth/refresh').status_code==200
    client.cookies.set('lab_refresh',old,domain='testserver.local',path='/api/v1/auth')
    assert mutate(client,'/auth/refresh').status_code==401
    assert client.get('/api/v1/auth/me').status_code==401


def test_soft_delete_blocks_existing_access(client):
    """Confere que excluir logicamente a conta bloqueia uma sessão já emitida.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    activate_admin(client)
    async def disable():
        """Marca a conta fictícia como excluída usando a conexão do fixture.

        Returns:
            None: Altera apenas o registro dentro da transação externa do caso.
        """
        async with client.app.state.db_pool.acquire() as connection:
            await connection.execute("UPDATE users SET soft_delete=TRUE WHERE email='admin@example.com'")
    client.portal.call(disable)
    assert client.get('/api/v1/auth/me').status_code==401


def test_interface_security_and_markup(client):
    """Confere entrega da interface, recursos estáticos e cabeçalhos de proteção.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    response=client.get('/lab')
    assert response.status_code==200
    assert 'lang="pt-BR"' in response.text
    assert 'frame-ancestors' in response.headers['content-security-policy']
    assert client.get('/static/lab.js').status_code==200
    assert mutate(client,'/auth/login',{'email':'admin@example.com','password':'wrong'}).status_code==401


def test_limits_and_extra_input(client):
    """Confere limite de corpo e recusa de autoria enviada pelo cliente.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    response=client.post('/api/v1/auth/login',content=b'x'*(256*1024+1))
    assert response.status_code==413
    activate_admin(client)
    body={'name':'Ana','email':'ana@example.com','temporary_password':'Temporary!Ana2026','role_code':'N3','created_by':str(uuid4())}
    assert mutate(client,'/access-requests',body).status_code==422


def test_failure_counters_survive_new_login_and_quality_does_not_count(client):
    """Confere o bloqueio por reprovações reais sem contar captura ruim nem permitir zerar
    falhas com novo login.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    activate_admin(client)
    team=client.get('/api/v1/teams').json()['data']['items'][0]['id']
    body=dict(name='Biometria',email='bio@example.com',role_code='N1',team_id=team,temporary_password='Temporary!Bio2026')
    assert mutate(client,'/access-requests',body).status_code==201
    mutate(client,'/auth/logout')
    credentials={'email':body['email'],'password':body['temporary_password']}
    assert mutate(client,'/auth/login',credentials).status_code==200
    async def poor_quality(contents,reference):
        """Simula uma captura sem qualidade sem executar modelos reais.

        Args:
            contents: Arquivos ignorados pelo stub.
            reference: Template ignorado pelo stub.

        Raises:
            BiometricError: Sempre lança a categoria quality para verificar o contador.
        """
        raise BiometricError('Captura ruim','quality')
    client.app.state.inference=poor_quality
    assert mutate(client,'/auth/biometric/enroll',files=frames()).status_code==422
    async def count():
        """Consulta o contador de falhas da conta fictícia deste cenário.

        Returns:
            int: Quantidade atual de reprovações biométricas no fixture.
        """
        async with client.app.state.db_pool.acquire() as connection:
            return await connection.fetchval("SELECT biometric_failure_count FROM users WHERE email='bio@example.com'")
    assert client.portal.call(count)==0
    async def rejected(contents,reference):
        """Simula uma reprovação antifraude real para o controle de tentativas.

        Args:
            contents: Arquivos ignorados pelo stub.
            reference: Template ignorado pelo stub.

        Raises:
            BiometricError: Sempre lança a categoria rejected, que deve incrementar o
                contador.
        """
        raise BiometricError('PAD reprovado','rejected')
    client.app.state.inference=rejected
    for _ in range(3):
        assert mutate(client,'/auth/biometric/enroll',files=frames()).status_code==401
        response=mutate(client,'/auth/login',credentials)
    assert response.status_code==429
    assert client.portal.call(count)==3


def test_bootstrap_idempotency_keeps_admin_password(client):
    """Confere que repetir o seed não redefine a senha definitiva do ADMIN.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    activate_admin(client)
    async def repeat():
        """Repete o seed com outra temporária para testar idempotência.

        Returns:
            None: Executa o bootstrap sem substituir a senha de uma conta existente.
        """
        from facial_recognition.seed import run_seeds
        async with client.app.state.db_pool.acquire() as connection:
            await run_seeds(connection,'admin@example.com','Another!Temporary2026')
    client.portal.call(repeat)
    mutate(client,'/auth/logout')
    response=mutate(client,'/auth/login',{'email':'admin@example.com','password':FINAL_PASSWORD})
    assert response.json()['data']['next_step']=='SESSION'


def test_stage_rotation_invalidates_previous_token(client):
    """Confere que a troca do jti invalida o cookie restrito anterior.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    from conftest import ADMIN_PASSWORD
    response=mutate(client,'/auth/login',{'email':'admin@example.com','password':ADMIN_PASSWORD})
    old_stage=client.cookies.get('lab_stage')
    assert response.status_code==200
    assert mutate(client,'/auth/login',{'email':'admin@example.com','password':ADMIN_PASSWORD}).status_code==200
    client.cookies.set('lab_stage',old_stage,domain='testserver.local',path='/api/v1/auth')
    assert client.get('/api/v1/auth/flow').status_code==401


def test_relogin_revokes_previous_session_even_without_access_cookie(client):
    """Confere a revogação do contexto anterior pelo refresh quando o access está ausente.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    activate_admin(client)
    old_access=client.cookies.get('lab_access')
    client.cookies.delete('lab_access',domain='testserver.local',path='/api/v1')
    response=mutate(client,'/auth/login',{'email':'admin@example.com','password':FINAL_PASSWORD})
    assert response.status_code==200
    client.cookies.set('lab_access',old_access,domain='testserver.local',path='/api/v1')
    assert client.get('/api/v1/auth/me').status_code==401


def test_timeout_keeps_inference_slot_until_worker_finishes(monkeypatch):
    """Confere que o timeout não libera a vaga enquanto a thread continua trabalhando.

    Args:
        monkeypatch: Fixture pytest que restaura atributos e substituições ao terminar o
            caso.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    import asyncio
    import threading
    from facial_recognition.app import Inference
    release=threading.Event()
    class SlowModels:
        """Simula uma inferência que continua ocupada até receber um sinal de liberação.

        Captura o evento release do teste e não utiliza arquivos de modelos ou câmera.
        """
        def evaluate(self,contents,reference):
            """Aguarda o sinal controlado pelo teste antes de devolver um vetor fictício.

            A espera tem limite de dois segundos para não deixar a thread presa se o teste
            falhar.

            Args:
                contents: Arquivos ignorados nesta simulação de duração.
                reference: Referência ignorada nesta simulação de duração.

            Returns:
                numpy.ndarray: Vetor float32 de 128 posições; não representa identidade
                    real.
            """
            release.wait(timeout=2)
            return np.ones(128,dtype=np.float32)
    original_wait_for=asyncio.wait_for
    async def fast_timeout(awaitable,timeout):
        """Substitui o prazo da espera por um intervalo curto para acelerar o teste.

        Args:
            awaitable: Operação que será aguardada pelo asyncio.
            timeout: Prazo solicitado pela produção, substituído por 0,01 segundo neste
                caso.

        Returns:
            Any: Resultado da operação quando termina antes do limite simulado.

        Raises:
            TimeoutError: Quando a operação não termina no intervalo reduzido.
        """
        return await original_wait_for(awaitable,timeout=0.01)
    monkeypatch.setattr(asyncio,'wait_for',fast_timeout)
    async def scenario():
        """Verifica a ocupação da vaga após timeout e libera a thread ao terminar.

        Returns:
            None: Conclui as asserções e aguarda o encerramento da inferência.

        Raises:
            AssertionError: Se o timeout ou a recusa busy não forem observados.
        """
        inference=Inference(SlowModels())
        try:
            with pytest.raises(BiometricError) as error:await inference([],None)
            assert error.value.kind=='unavailable'
            with pytest.raises(BiometricError) as error:await inference([],None)
            assert error.value.kind=='busy'
        finally:
            release.set()
            if inference.task:await inference.task
    asyncio.run(scenario())


def test_startup_seed_preserves_existing_admin_when_settings_change(client):
    """Confere que novas configurações do seed não duplicam o ADMIN já existente.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    from facial_recognition.seed import run_seeds
    async def repeat():
        """Repete o seed com outro email e senha curta após o ADMIN já existir.

        A senha inválida não deve ser avaliada quando não há conta a criar.

        Returns:
            int: Quantidade de contas ADMIN após a repetição.
        """
        async with client.app.state.db_pool.acquire() as connection:
            # Senha inválida não interfere quando não há ADMIN a criar.
            await run_seeds(connection,'different@example.com','short')
            return await connection.fetchval("SELECT count(*) FROM users u JOIN roles r ON r.id=u.role_id WHERE r.code='ADMIN'")
    assert client.portal.call(repeat)==1
    activate_admin(client)
