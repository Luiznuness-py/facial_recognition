"""API test e pytest compartilham DB_NAME/schema test; dados de testes têm rollback."""
import asyncio
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

os.environ['ENVIRONMENT'] = 'test'
os.environ['BIOMETRICS_MODE'] = 'real'
os.environ['SECRET_KEY'] = 'isolated-test-key-32-bytes-minimum-2026'
os.environ.setdefault('ADMIN_SECRET','Temporary!Lab2026')

import numpy as np
import pytest
from fastapi.testclient import TestClient

from facial_recognition.app import app
from facial_recognition.core.settings import settings
from facial_recognition.core.database import create_pool, run_migrations

ADMIN_PASSWORD = 'Temporary!Lab2026'
FINAL_PASSWORD = 'Personal!Lab2026'


class TransactionPool:
    """Adapta uma conexão para o contrato de pool usado no lifespan dos testes.

    Todas as aquisições usam a mesma conexão dentro da transação externa do fixture.
    Transações das rotas tornam-se savepoints; este adaptador não deve ser usado em
    produção.

    Attributes:
        connection: Conexão de propriedade do fixture, que fará o rollback final.
    """

    def __init__(self, connection):
        """Associa a conexão transacional de propriedade do fixture.

        Args:
            connection: Conexão asyncpg que será compartilhada apenas neste caso de teste.
        """
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        """Entrega a conexão existente sem adquirir uma conexão adicional.

        Yields:
            asyncpg.Connection: Mesma conexão mantida pela transação externa do teste.
        """
        yield self.connection

    async def close(self):
        """Mantém o fechamento da conexão sob responsabilidade do fixture.

        Returns:
            None: Não fecha a conexão compartilhada para permitir o rollback externo.
        """
        pass  # O fixture é dono da conexão e executa o rollback externo.


@pytest.fixture
def client():
    """Prepara um cliente HTTP e o banco transacional para um caso de integração.

    Usa DB_NAME/schema test. Aplica migrations e limpa as tabelas dentro de uma transação
    externa que será revertida, restaurando cadastros anteriores. A conexão é compartilhada
    pelo adaptador; middleware e contexto do app são restaurados ao final. Não suporta casos
    paralelos sobre o mesmo schema.

    Yields:
        TestClient: Cliente HTTPS de teste, com lifespan e seed reais e inferência
            substituída.
    """
    @asynccontextmanager
    async def lifespan(application):
        """Executa a inicialização real sobre a conexão transacional do teste.

        Restaura registros por rollback em finally e fecha o pool original. Somente as
        credenciais iniciais do ADMIN, o carregamento dos modelos e a inferência são
        substituídos no contexto do caso.

        Args:
            application: Instância FastAPI que receberá o pool adaptado e o stub de
                inferência.

        Yields:
            None: Libera o cliente depois de preparar os fixtures e os seeds.
        """
        pool = await create_pool()
        try:
            await run_migrations(pool)
            async with pool.acquire() as connection:
                transaction = connection.transaction()
                await transaction.start()
                try:
                    # Isola fixtures de cadastros manuais; o rollback restaura tudo.
                    # TRUNCATE bloqueia as tabelas somente enquanto este teste roda.
                    tables = await connection.fetch("SELECT tablename FROM pg_tables WHERE schemaname='test' AND tablename<>'schema_migrations'")
                    names = ', '.join('test."'+row['tablename'].replace('"','""')+'"' for row in tables)
                    if names:
                        await connection.execute('TRUNCATE '+names+' RESTART IDENTITY CASCADE')
                    with patch('facial_recognition.app.create_pool', new=AsyncMock(return_value=TransactionPool(connection))), \
                         patch('facial_recognition.app.FaceModels.load'), \
                         patch.object(settings, 'ADMIN_EMAIL', 'admin@example.com'), \
                         patch.object(settings, 'ADMIN_SECRET', ADMIN_PASSWORD):
                        async with previous(application):
                            async def inference(contents, reference):
                                # Stub só para transições; modelos reais têm testes próprios.
                                """Simula uma aprovação biométrica para testar transições sem
                                depender da câmera.

                                É apenas um substituto de teste; não detecta rosto,
                                identidade ou fraude. Pesos reais são exercitados em testes
                                separados.

                                Args:
                                    contents: Arquivos recebidos, ignorados pelo stub.
                                    reference: Referência facial recebida, ignorada pelo
                                        stub.

                                Returns:
                                    numpy.ndarray: Vetor fixo de 128 posições com norma
                                        unitária.
                                """
                                return np.ones(128,dtype=np.float32)/np.sqrt(128)
                            application.state.inference=inference
                            yield
                finally:
                    await transaction.rollback()
        finally:
            await pool.close()
    previous = app.router.lifespan_context
    app.router.lifespan_context=lifespan
    app.middleware_stack=None
    try:
        with TestClient(app,base_url='https://testserver') as test_client:
            yield test_client
    finally:
        app.router.lifespan_context=previous


def mutate(client,path,body=None,files=None):
    """Envia um POST protegido por CSRF para a API do fixture.

    Busca uma assinatura CSRF atual antes da alteração e envia Origin da própria origem de
    teste.

    Args:
        client: TestClient com o contexto de cookies do cenário.
        path: Caminho relativo a /api/v1.
        body: Corpo JSON opcional.
        files: Arquivos multipart opcionais no formato aceito pelo cliente HTTP.

    Returns:
        httpx.Response: Resposta completa, inclusive para erros esperados.
    """
    token=client.get('/api/v1/auth/csrf').json()['data']['csrf_token']
    return client.post('/api/v1'+path,json=body,files=files,
        headers={'Origin':'https://testserver','X-CSRF-Token':token})


def activate_admin(client):
    """Conclui a primeira entrada do ADMIN fictício usado nos testes.

    Usa apenas as constantes fictícias do fixture; as gravações são revertidas pela
    transação externa.

    Args:
        client: Cliente do fixture, iniciado com a temporária de teste.

    Returns:
        httpx.Response: Resposta da conclusão com sessão completa.

    Raises:
        AssertionError: Se login, etapa esperada ou definição da senha falharem.
    """
    response=mutate(client,'/auth/login',{'email':'admin@example.com','password':ADMIN_PASSWORD})
    assert response.status_code==200,response.text
    assert response.json()['data']['next_step']=='CHANGE_PASSWORD'
    response=mutate(client,'/auth/password/complete',{'new_password':FINAL_PASSWORD,'password_confirmation':FINAL_PASSWORD})
    assert response.status_code==200,response.text
    return response
