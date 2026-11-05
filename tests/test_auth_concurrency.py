"""Regressões de sessão em conexões independentes e schema aleatório descartável."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi import HTTPException, Request, Response

from facial_recognition.core.accounts import revoke_access
from facial_recognition.core.database import run_migrations
from facial_recognition.core.security import token_hash
from facial_recognition.core.settings import settings
from facial_recognition.core.token_jwt import TokenJwt
from facial_recognition.routers.auth import refresh, logout, login, password_change_complete
from facial_recognition.schemas.password_hashes import PasswordCompleteRequest
from facial_recognition.schemas.sessions import LoginRequest
from facial_recognition.seed import run_seeds
from facial_recognition.utils.utils import audit


@asynccontextmanager
async def auth_database():
    """Isola commits concorrentes sem tocar nas tabelas public ou test.

    Cria um schema aleatório, aplica migrations/seeds e permite commits em conexões
    independentes. Fecha o pool e remove apenas esse schema em finally.

    Yields:
        tuple: Pool isolado, UUID da conta e registro da sessão com refresh fictício.
    """
    schema='auth_race_'+uuid4().hex
    control=await asyncpg.connect(settings.get_database_url())
    pool=None
    try:
        await control.execute('CREATE SCHEMA '+schema)
        pool=await asyncpg.create_pool(settings.get_database_url(),min_size=2,max_size=4,server_settings={'search_path':schema})
        await run_migrations(pool)
        async with pool.acquire() as c:
            async with c.transaction():
                await run_seeds(c,email='race.admin@example.com',password='Temporary!Race2026')
                user=await c.fetchval("UPDATE users SET status='ACTIVE',activated_at=NOW(),password_change_required=FALSE RETURNING id")
                session=await c.fetchrow("INSERT INTO sessions(user_id,expires_at) VALUES($1,NOW()+INTERVAL '24 hours') RETURNING *",user)
                await c.execute('INSERT INTO refresh_tokens(session_id,token_hash,expires_at) VALUES($1,$2,$3)',session['id'],token_hash('race-refresh'),session['expires_at'])
        yield pool,user,session
    finally:
        if pool:
            await pool.close()
        await control.execute('DROP SCHEMA '+schema+' CASCADE')
        await control.close()


def refresh_request():
    """Usa transporte HTTPS e emissor reais, com credencial fictícia do fixture.

    Monta uma Request HTTPS com TokenJwt real e refresh fictício, sem executar dependências HTTP
    ou abrir conexões.

    Returns:
        Request: Requisição do cenário para chamar a rota de refresh diretamente.
    """
    return Request({'type':'http','scheme':'https','path':'/api/v1/auth/refresh',
        'headers':[(b'cookie',b'lab_refresh=race-refresh'),(b'host',b'testserver')],
        'server':('testserver',443),'query_string':b'',
        'app':SimpleNamespace(state=SimpleNamespace(tokens=TokenJwt()))})


def test_refresh_revalidates_after_concurrent_revocation():
    """Revogação entre localização e lock do refresh termina em 401, sem deadlock.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    async def scenario():
        """Executa o cenário concorrente em conexões independentes e schema descartável.

        Coordena as chamadas com eventos ou locks reais e verifica os invariantes antes de
        liberar o schema exclusivo do teste.

        Returns:
            None: Contexto assíncrono encerrado após as verificações do cenário.

        Raises:
            AssertionError: Quando uma disputa viola o estado, a autorização ou o histórico
                esperado.
        """
        async with auth_database() as (pool,user,session):
            located=asyncio.Event()
            revoked=asyncio.Event()
            class RefreshConnection:
                """Intercala a operação exatamente após a localização inicial do token."""
                def __init__(self,c):
                    """Associa a conexão real ao adaptador de sincronização ou contagem do teste.

                    Args:
                        c: Conexão independente mantida pelo cenário de concorrência.

                    Returns:
                        None: Adaptador inicializado sem abrir ou fechar a conexão recebida.
                    """
                    self.c=c
                def __getattr__(self,name):
                    """Encaminha atributos não interceptados à conexão real do cenário.

                    Args:
                        name: Nome do atributo a encaminhar à conexão real encapsulada.

                    Returns:
                        Any: Atributo ou método da conexão; chamadas contadas recebem o wrapper
                            local.

                    Raises:
                        AttributeError: Quando a conexão real também não possui o atributo
                            solicitado.
                    """
                    return getattr(self.c,name)
                async def fetchrow(self,sql,*args):
                    """Executa a consulta real e sincroniza o cenário após adquirir o lock alvo.

                    Args:
                        sql: Consulta SQL controlada pelo teste, encaminhada ao PostgreSQL real.
                        args: Argumentos posicionais encaminhados sem alteração à chamada
                            encapsulada.

                    Returns:
                        asyncpg.Record | None: Linha retornada pela consulta original.

                    Raises:
                        asyncpg.PostgresError: Quando a operação real no schema isolado falha.
                    """
                    row=await self.c.fetchrow(sql,*args)
                    if 'FROM refresh_tokens WHERE token_hash=' in sql and not located.is_set():
                        located.set()
                        await revoked.wait()
                    return row
            class RevokeConnection:
                """Libera o refresh depois de a revogação deter o lock da sessão."""
                def __init__(self,c):
                    """Associa a conexão real ao adaptador de sincronização ou contagem do teste.

                    Args:
                        c: Conexão independente mantida pelo cenário de concorrência.

                    Returns:
                        None: Adaptador inicializado sem abrir ou fechar a conexão recebida.
                    """
                    self.c=c
                def __getattr__(self,name):
                    """Encaminha atributos não interceptados à conexão real do cenário.

                    Args:
                        name: Nome do atributo a encaminhar à conexão real encapsulada.

                    Returns:
                        Any: Atributo ou método da conexão; chamadas contadas recebem o wrapper
                            local.

                    Raises:
                        AttributeError: Quando a conexão real também não possui o atributo
                            solicitado.
                    """
                    return getattr(self.c,name)
                async def execute(self,sql,*args):
                    """Executa a escrita real e sinaliza a revogação da sessão quando aplicável.

                    Args:
                        sql: Consulta SQL controlada pelo teste, encaminhada ao PostgreSQL real.
                        args: Argumentos posicionais encaminhados sem alteração à chamada
                            encapsulada.

                    Returns:
                        str: Comando e quantidade de registros afetados pelo PostgreSQL.

                    Raises:
                        asyncpg.PostgresError: Quando a operação real no schema isolado falha.
                    """
                    result=await self.c.execute(sql,*args)
                    if sql.startswith('UPDATE sessions SET revoked_at=NOW()'):
                        revoked.set()
                    return result
            async def renew():
                """Executa uma rotação real de refresh na conexão independente deste competidor.

                Returns:
                    ApiResponse[RefreshTokenResponse]: Rotação concluída, quando a credencial é
                        aceita.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    return await refresh(refresh_request(),Response(),RefreshConnection(c))
            async def revoke():
                """Revoga o acesso na conexão independente após a sincronização prevista pelo cenário.

                Returns:
                    None: Operação concluída e verificações satisfeitas, quando presentes.
                """
                await located.wait()
                async with pool.acquire() as c:
                    async with c.transaction():
                        await c.fetchrow('SELECT id FROM users WHERE id=$1 FOR UPDATE',user)
                        await revoke_access(RevokeConnection(c),user)
            results=await asyncio.wait_for(asyncio.gather(renew(),revoke(),return_exceptions=True),8)
            assert isinstance(results[0],HTTPException) and results[0].status_code==401,results
            assert results[1] is None,results
            async with pool.acquire() as c:
                assert await c.fetchval('SELECT revoked_at IS NOT NULL FROM sessions WHERE id=$1',session['id'])
                assert await c.fetchval('SELECT count(*) FROM refresh_tokens')==1
                assert await c.fetchval('SELECT bool_and(revoked_at IS NOT NULL) FROM refresh_tokens')
    asyncio.run(scenario())


def test_concurrent_refresh_replay_revokes_the_successor():
    """Só uma rotação vence; replay encerra a sessão sem ampliar sua expiração.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    async def scenario():
        """Executa o cenário concorrente em conexões independentes e schema descartável.

        Coordena as chamadas com eventos ou locks reais e verifica os invariantes antes de
        liberar o schema exclusivo do teste.

        Returns:
            None: Contexto assíncrono encerrado após as verificações do cenário.

        Raises:
            AssertionError: Quando uma disputa viola o estado, a autorização ou o histórico
                esperado.
        """
        async with auth_database() as (pool,user,session):
            async def renew():
                """Executa uma rotação real de refresh na conexão independente deste competidor.

                Returns:
                    ApiResponse[RefreshTokenResponse]: Rotação concluída, quando a credencial é
                        aceita.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    return await refresh(refresh_request(),Response(),c)
            results=await asyncio.wait_for(asyncio.gather(renew(),renew(),return_exceptions=True),8)
            assert sum(isinstance(r,HTTPException) and r.status_code==401 for r in results)==1,results
            assert sum(not isinstance(r,BaseException) for r in results)==1,results
            async with pool.acquire() as c:
                assert await c.fetchval('SELECT revoked_at IS NOT NULL FROM sessions WHERE id=$1',session['id'])
                tokens=await c.fetch('SELECT * FROM refresh_tokens ORDER BY used_at NULLS LAST')
                assert len(tokens)==2
                assert tokens[0]['replaced_by_id']==tokens[1]['id']
                assert all(t['expires_at']==session['expires_at'] for t in tokens)
            with pytest.raises(HTTPException) as error:
                async with pool.acquire() as c:
                    await refresh(refresh_request(),Response(),c)
            assert error.value.status_code==401
    asyncio.run(scenario())


def test_revocation_waiting_for_refresh_also_revokes_new_token():
    """Se a rotação vencer, a revogação subsequente alcança o token recém-criado.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    async def scenario():
        """Executa o cenário concorrente em conexões independentes e schema descartável.

        Coordena as chamadas com eventos ou locks reais e verifica os invariantes antes de
        liberar o schema exclusivo do teste.

        Returns:
            None: Contexto assíncrono encerrado após as verificações do cenário.

        Raises:
            AssertionError: Quando uma disputa viola o estado, a autorização ou o histórico
                esperado.
        """
        async with auth_database() as (pool,user,session):
            session_locked=asyncio.Event()
            user_locked=asyncio.Event()
            async def renew():
                """Executa uma rotação real de refresh na conexão independente deste competidor.

                Returns:
                    ApiResponse[RefreshTokenResponse]: Rotação concluída, quando a credencial é
                        aceita.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    async with c.transaction():
                        await c.fetchrow('SELECT id FROM sessions WHERE id=$1 FOR UPDATE',session['id'])
                        session_locked.set()
                        await user_locked.wait()
                        return await refresh(refresh_request(),Response(),c)
            async def revoke():
                """Revoga o acesso na conexão independente após a sincronização prevista pelo cenário.

                Returns:
                    None: Operação concluída e verificações satisfeitas, quando presentes.
                """
                await session_locked.wait()
                async with pool.acquire() as c:
                    async with c.transaction():
                        await c.fetchrow('SELECT id FROM users WHERE id=$1 FOR UPDATE',user)
                        user_locked.set()
                        await revoke_access(c,user)
            results=await asyncio.wait_for(asyncio.gather(renew(),revoke(),return_exceptions=True),8)
            assert not any(isinstance(r,BaseException) for r in results),results
            async with pool.acquire() as c:
                assert await c.fetchval('SELECT count(*) FROM refresh_tokens')==2
                assert await c.fetchval('SELECT bool_and(revoked_at IS NOT NULL) FROM refresh_tokens')
                assert await c.fetchval('SELECT revoked_at IS NOT NULL FROM sessions WHERE id=$1',session['id'])
    asyncio.run(scenario())


def test_account_switch_does_not_block_concurrent_administrative_audit():
    """Locks de contas não bloqueiam a FK do autor da revogação em outra conexão.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    async def scenario():
        """Executa o cenário concorrente em conexões independentes e schema descartável.

        Coordena as chamadas com eventos ou locks reais e verifica os invariantes antes de
        liberar o schema exclusivo do teste.

        Returns:
            None: Contexto assíncrono encerrado após as verificações do cenário.

        Raises:
            AssertionError: Quando uma disputa viola o estado, a autorização ou o histórico
                esperado.
        """
        async with auth_database() as (pool,admin,session):
            other=UUID('ffffffff-ffff-ffff-ffff-ffffffffffff')
            async with pool.acquire() as c:
                await c.execute("INSERT INTO users(id,name,email,role_id) SELECT $1,'Outro','other@example.com',id FROM roles WHERE code='N3'",other)
                sid=await c.fetchval("INSERT INTO sessions(user_id,expires_at) VALUES($1,NOW()+INTERVAL '24 hours') RETURNING id",other)
            request=refresh_request()
            access=request.app.state.tokens.create_token(other,'ACCESS',900,session_id=str(sid))
            request.scope['headers']=[(b'cookie',('lab_access='+access).encode()),(b'host',b'testserver')]
            request.state.request_id=uuid4()
            revoked=asyncio.Event()
            waiting=asyncio.Event()
            async with pool.acquire() as revoker, pool.acquire() as browser, pool.acquire() as observer:
                async def revoke():
                    """Revoga o acesso na conexão independente após a sincronização prevista pelo cenário.

                    Returns:
                        None: Operação concluída e verificações satisfeitas, quando presentes.
                    """
                    async with revoker.transaction():
                        await revoker.fetchrow('SELECT id FROM users WHERE id=$1 FOR UPDATE',other)
                        await revoke_access(revoker,other)
                        revoked.set()
                        await waiting.wait()
                        await audit(revoker,admin,'USER_RECOVERY_AUTHORIZED','users',other,request_id=request.state.request_id)
                async def switch():
                    """Inicia login na conta ADMIN preservando o contexto anterior do navegador.

                    Returns:
                        ApiResponse[LoginResponse]: Etapa ou sessão emitida para a conta ADMIN.

                    Raises:
                        HTTPException: Quando a revalidação do fluxo recusa a credencial, o
                            vínculo ou o estado concorrente.
                    """
                    await revoked.wait()
                    return await login(LoginRequest(email='race.admin@example.com',password='Temporary!Race2026'),request,Response(),browser)
                async def observe():
                    """Espera o PostgreSQL informar o bloqueio entre os PIDs e libera a auditoria concorrente.

                    Returns:
                        None: Operação concluída e verificações satisfeitas, quando presentes.
                    """
                    await revoked.wait()
                    while not await observer.fetchval('SELECT $1::int=ANY(pg_blocking_pids($2))',revoker.get_server_pid(),browser.get_server_pid()):
                        await asyncio.sleep(.01)
                    waiting.set()
                results=await asyncio.wait_for(asyncio.gather(revoke(),switch(),observe(),return_exceptions=True),8)
                assert not any(isinstance(r,BaseException) for r in results),results
                assert await observer.fetchval("SELECT count(*) FROM audit_events WHERE event='USER_RECOVERY_AUTHORIZED'")==1
    asyncio.run(scenario())


@pytest.mark.parametrize('action',['logout','login'])
def test_browser_switch_during_password_change_has_no_lock_inversion(action):
    """Sair ou entrar em outra conta não inverte sessão/tentativa com a troca de senha.

    Args:
        action: Ação concorrente parametrizada: logout ou login em outra conta.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    async def scenario():
        """Executa o cenário concorrente em conexões independentes e schema descartável.

        Coordena as chamadas com eventos ou locks reais e verifica os invariantes antes de
        liberar o schema exclusivo do teste.

        Returns:
            None: Contexto assíncrono encerrado após as verificações do cenário.

        Raises:
            AssertionError: Quando uma disputa viola o estado, a autorização ou o histórico
                esperado.
        """
        async with auth_database() as (pool,user,session):
            async with pool.acquire() as c:
                attempt=await c.fetchrow('''INSERT INTO authentication_attempts(user_id,stage,token_jti,expires_at,operation,initiating_session_id)
                    VALUES($1,'CHANGE_PASSWORD',$2,NOW()+INTERVAL '5 minutes','PASSWORD_CHANGE',$3) RETURNING *''',user,uuid4(),session['id'])
                await c.execute('UPDATE password_hashes SET is_temporary=FALSE,temporary_expires_at=NULL WHERE user_id=$1',user)
                other=await c.fetchval('''INSERT INTO users(name,email,role_id,status,activated_at,password_change_required,biometric_enrollment_required)
                    SELECT 'Outro','other@example.com',id,'ACTIVE',NOW(),FALSE,FALSE FROM roles WHERE code='N3' RETURNING id''')
                await c.execute('''INSERT INTO password_hashes(user_id,password_hash,is_temporary)
                    SELECT $1,password_hash,FALSE FROM password_hashes WHERE user_id=$2''',other,user)
            request=refresh_request()
            tokens=request.app.state.tokens
            access=tokens.create_token(user,'ACCESS',900,session_id=str(session['id']))
            stage=tokens.create_token(user,'RESTRICTED',300,attempt_id=str(attempt['id']),stage='CHANGE_PASSWORD',operation='PASSWORD_CHANGE',jti=str(attempt['token_jti']))
            request.scope['headers']=[(b'cookie',('lab_access='+access+'; lab_stage='+stage).encode()),(b'host',b'testserver')]
            request.state.request_id=uuid4()
            attempt_locked=asyncio.Event()
            logout_started=asyncio.Event()
            class ChangeConnection:
                """Suspende a troca somente depois do lock real da tentativa."""
                def __init__(self,c):
                    """Associa a conexão real ao adaptador de sincronização ou contagem do teste.

                    Args:
                        c: Conexão independente mantida pelo cenário de concorrência.

                    Returns:
                        None: Adaptador inicializado sem abrir ou fechar a conexão recebida.
                    """
                    self.c=c
                def __getattr__(self,name):
                    """Encaminha atributos não interceptados à conexão real do cenário.

                    Args:
                        name: Nome do atributo a encaminhar à conexão real encapsulada.

                    Returns:
                        Any: Atributo ou método da conexão; chamadas contadas recebem o wrapper
                            local.

                    Raises:
                        AttributeError: Quando a conexão real também não possui o atributo
                            solicitado.
                    """
                    return getattr(self.c,name)
                async def fetchrow(self,sql,*args):
                    """Executa a consulta real e sincroniza o cenário após adquirir o lock alvo.

                    Args:
                        sql: Consulta SQL controlada pelo teste, encaminhada ao PostgreSQL real.
                        args: Argumentos posicionais encaminhados sem alteração à chamada
                            encapsulada.

                    Returns:
                        asyncpg.Record | None: Linha retornada pela consulta original.

                    Raises:
                        asyncpg.PostgresError: Quando a operação real no schema isolado falha.
                    """
                    row=await self.c.fetchrow(sql,*args)
                    if 'FROM authentication_attempts WHERE id=' in sql and 'FOR UPDATE' in sql:
                        attempt_locked.set()
                        await logout_started.wait()
                    return row
            class LogoutConnection:
                """Detecta a primeira aquisição de lock do logout em ambas as ordens."""
                def __init__(self,c):
                    """Associa a conexão real ao adaptador de sincronização ou contagem do teste.

                    Args:
                        c: Conexão independente mantida pelo cenário de concorrência.

                    Returns:
                        None: Adaptador inicializado sem abrir ou fechar a conexão recebida.
                    """
                    self.c=c
                def __getattr__(self,name):
                    """Encaminha atributos não interceptados à conexão real do cenário.

                    Args:
                        name: Nome do atributo a encaminhar à conexão real encapsulada.

                    Returns:
                        Any: Atributo ou método da conexão; chamadas contadas recebem o wrapper
                            local.

                    Raises:
                        AttributeError: Quando a conexão real também não possui o atributo
                            solicitado.
                    """
                    return getattr(self.c,name)
                async def fetch(self,sql,*args):
                    """Sinaliza a tentativa de lock da conta e encaminha a consulta real.

                    Args:
                        sql: Consulta SQL controlada pelo teste, encaminhada ao PostgreSQL real.
                        args: Argumentos posicionais encaminhados sem alteração à chamada
                            encapsulada.

                    Returns:
                        list[asyncpg.Record]: Linhas retornadas pela consulta original.

                    Raises:
                        asyncpg.PostgresError: Quando a operação real no schema isolado falha.
                    """
                    if 'FROM users' in sql and 'UPDATE' in sql:
                        logout_started.set()
                    return await self.c.fetch(sql,*args)
                async def execute(self,sql,*args):
                    """Executa a escrita real e sinaliza a revogação da sessão quando aplicável.

                    Args:
                        sql: Consulta SQL controlada pelo teste, encaminhada ao PostgreSQL real.
                        args: Argumentos posicionais encaminhados sem alteração à chamada
                            encapsulada.

                    Returns:
                        str: Comando e quantidade de registros afetados pelo PostgreSQL.

                    Raises:
                        asyncpg.PostgresError: Quando a operação real no schema isolado falha.
                    """
                    result=await self.c.execute(sql,*args)
                    if sql.startswith('UPDATE sessions SET revoked_at=NOW()'):
                        logout_started.set()
                    return result
            async def change():
                """Conclui a troca de senha real enquanto a ação concorrente disputa os locks.

                Returns:
                    ApiResponse[LoginRequiredResponse]: Confirmação da troca e exigência de nova
                        entrada.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    return await password_change_complete(PasswordCompleteRequest(new_password='Changed!Race2026',password_confirmation='Changed!Race2026'),request,Response(),ChangeConnection(c),attempt)
            async def leave():
                """Espera o lock da tentativa e executa login ou logout na outra conexão.

                Returns:
                    Response | ApiResponse: Resultado real de logout ou do login parametrizado.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                await attempt_locked.wait()
                async with pool.acquire() as c:
                    if action=='login':
                        return await login(LoginRequest(email='other@example.com',password='Temporary!Race2026'),request,Response(),LogoutConnection(c))
                    return await logout(request,LogoutConnection(c))
            results=await asyncio.wait_for(asyncio.gather(change(),leave(),return_exceptions=True),8)
            assert not any(isinstance(r,BaseException) for r in results),results
            if action=='logout':
                assert results[1].status_code==204
            else:
                assert results[1].data['next_step']=='VERIFY_FACE'
            async with pool.acquire() as c:
                assert await c.fetchval('SELECT bool_and(revoked_at IS NOT NULL) FROM sessions')
                assert await c.fetchval("SELECT status FROM authentication_attempts WHERE id=$1",attempt['id'])=='COMPLETED'
    asyncio.run(scenario())
