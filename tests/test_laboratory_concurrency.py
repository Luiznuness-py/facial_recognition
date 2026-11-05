"""Concorrência em conexões independentes e schema descartável exclusivo deste teste."""
import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
from fastapi import HTTPException

from facial_recognition.core.database import run_migrations
from facial_recognition.core.settings import settings
from facial_recognition.core import laboratory as lab
from facial_recognition.seed import run_seeds
from facial_recognition.seed.development import seed_development
from facial_recognition.routers.vault import send_report, publish, keep_restricted
from facial_recognition.routers.validations import responsible, analysis, add_participant
from facial_recognition.schemas.vault import VaultSend, VaultDecisionReason
from facial_recognition.schemas.validations import ValidationResponsibleUpdate, ValidationAnalysisUpdate
from facial_recognition.schemas.validation_participants import ValidationParticipantAdd


def test_simultaneous_creation_submission_and_decision():
    """Amostra, entrega e decisão permanecem únicas sob duas chamadas simultâneas.

    Returns:
        None: O cenário termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado diverge do resultado esperado.
    """
    async def scenario():
        """Cria e remove somente seu schema aleatório, mesmo quando uma asserção falha.

        Coordena as chamadas com eventos ou locks reais e verifica os invariantes antes de
        liberar o schema exclusivo do teste.

        Returns:
            None: Contexto assíncrono encerrado após as verificações do cenário.

        Raises:
            AssertionError: Quando uma disputa viola o estado, a autorização ou o histórico
                esperado.
        """
        schema='race_'+uuid4().hex
        control=await asyncpg.connect(settings.get_database_url())
        pool=None
        try:
            await control.execute('CREATE SCHEMA '+schema)
            pool=await asyncpg.create_pool(settings.get_database_url(),min_size=2,max_size=4,server_settings={'search_path':schema})
            await run_migrations(pool)
            async with pool.acquire() as c:
                async with c.transaction():
                    await run_seeds(c,email='race.admin@example.com',password='Temporary!Race2026')
                    await seed_development(c)
                    people={r['email']:dict(r) for r in await c.fetch('SELECT u.*,r.code AS role FROM users u JOIN roles r ON r.id=u.role_id')}
                    owner=people['n1.a@example.com']
                    supervisor=people['n2.a@example.com']
                    authority=people['n3@example.com']
                    # A carga de desenvolvimento já prepara uma investigação para outro exercício.
                    a=await c.fetchrow('''INSERT INTO biological_agents(code,provisional_label,material_type,collection_location,collected_on,
                        initial_observations,investigation_reason,team_id,created_by)
                        VALUES('RACE','Amostra','Água','Local',CURRENT_DATE,'Observação','Motivo',$1,$2) RETURNING *''',owner['team_id'],owner['id'])
            async def create():
                """Cada chamada adquire sua própria conexão e aguarda o lock da amostra.

                Returns:
                    asyncpg.Record: Investigação criada se a reserva vencer a disputa.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    async with c.transaction():
                        locked=await lab.agent(c,a['id'],supervisor,True)
                        return await lab.create_validation(c,locked,owner['id'],supervisor['id'])
            results=await asyncio.gather(create(),create(),return_exceptions=True)
            assert sum(isinstance(r,HTTPException) and r.status_code==409 for r in results)==1
            row=next(r for r in results if not isinstance(r,BaseException))
            async with pool.acquire() as c:
                await c.execute("UPDATE validations SET assessments_performed='A',observed_results='B',technical_opinion='C',recommendation='D' WHERE id=$1",row['id'])
            async def submit():
                """Envia sob o mesmo lock usado pelas rotas HTTP.

                Returns:
                    dict: Confirmação da entrega única se o envio vencer a disputa.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    async with c.transaction():
                        current=await lab.validation(c,row['id'],owner,True)
                        return await lab.submit_analysis(c,current,owner,uuid4())
            results=await asyncio.gather(submit(),submit(),return_exceptions=True)
            assert sum(isinstance(r,HTTPException) and r.status_code==409 for r in results)==1
            request=SimpleNamespace(state=SimpleNamespace(request_id=uuid4()))
            async with pool.acquire() as c:
                assert await c.fetchval('SELECT count(*) FROM investigation_submissions WHERE validation_id=$1',row['id'])==1
                await send_report(row['id'],VaultSend(title='Relatório',final_conclusion='Conclusão',final_risk_percentage=0,public_title='Notícia',public_risk_category='LOW',public_body='Texto'),request,c,supervisor)
                vault_id=await c.fetchval('SELECT id FROM vault WHERE validation_id=$1',row['id'])
            async def decide(public):
                """Duas decisões incompatíveis competem pelo registro selado.

                Args:
                    public: Se True, tenta publicar; False tenta a decisão concorrente de
                        sigilo.

                Returns:
                    ApiResponse: Resultado da decisão N3 que vencer a disputa.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    if public:
                        return await publish(vault_id,request,c,authority)
                    return await keep_restricted(vault_id,VaultDecisionReason(reason='Reservado'),request,c,authority)
            results=await asyncio.gather(decide(True),decide(False),return_exceptions=True)
            assert sum(isinstance(r,HTTPException) and r.status_code==409 for r in results)==1
            assert sum(not isinstance(r,BaseException) for r in results)==1
            async with pool.acquire() as c:
                state=await c.fetchval('SELECT decision_status FROM vault WHERE id=$1',vault_id)
                count=await c.fetchval('SELECT count(*) FROM publications WHERE vault_id=$1',vault_id)
                assert count==(1 if state=='PUBLISHED' else 0)
                await c.execute("UPDATE users SET status='ACTIVE',activated_at=NOW(),password_change_required=FALSE,biometric_enrollment_required=FALSE")
            fresh=await create()
            colleague=people['colaborador.a@example.com']
            async def assign():
                """A troca compete com a escrita do responsável anterior pela mesma amostra.

                Returns:
                    ApiResponse[ValidationResponsibleResponse]: Novos vínculos de
                        responsabilidade/leitura.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    return await responsible(fresh['id'],ValidationResponsibleUpdate(responsible_user_id=colleague['id']),request,c,supervisor)
            async def draft():
                """Tenta salvar o rascunho do responsável anterior durante sua substituição.

                Returns:
                    ApiResponse[ValidationResponse]: Rascunho salvo se a responsabilidade ainda
                        for válida.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    return await analysis(fresh['id'],ValidationAnalysisUpdate(recommendation='Rascunho anterior'),request,c,owner)
            results=await asyncio.gather(assign(),draft(),return_exceptions=True)
            assert not isinstance(results[0],BaseException),results
            assert not isinstance(results[1],BaseException) or (isinstance(results[1],HTTPException) and results[1].status_code==403),results
            async with pool.acquire() as c:
                current=await lab.validation(c,fresh['id'],owner)
                assert current['responsible_user_id']==colleague['id']
                try:
                    lab.editable(current,owner,True)
                except HTTPException as error:
                    assert error.status_code==403
                else:
                    raise AssertionError('O responsável anterior ainda pode editar.')
                await c.execute("UPDATE validations SET assessments_performed='A',observed_results='B',technical_opinion='C',recommendation='D' WHERE id=$1",fresh['id'])
                async with c.transaction():
                    current=await lab.validation(c,fresh['id'],colleague,True)
                    await lab.submit_analysis(c,current,colleague,uuid4())
                snapshot=await c.fetchval('SELECT participants_snapshot FROM investigation_submissions WHERE validation_id=$1',fresh['id'])
                people_snapshot=json.loads(snapshot)
                assert [p['user_id'] for p in people_snapshot]==[str(colleague['id']),str(owner['id'])]
                await c.execute("UPDATE users SET name='Nome atualizado' WHERE id=$1",owner['id'])
                assert await c.fetchval('SELECT participants_snapshot FROM investigation_submissions WHERE validation_id=$1',fresh['id'])==snapshot
                shared=[]
                for index,person in enumerate((owner,colleague)):
                    sample=await c.fetchrow('''INSERT INTO biological_agents(code,provisional_label,material_type,collection_location,collected_on,
                        initial_observations,investigation_reason,team_id,created_by)
                        VALUES($1,'Amostra','Água','Local',CURRENT_DATE,'Observação','Motivo',$2,$3) RETURNING *''','SHARE-'+str(index),person['team_id'],person['id'])
                    shared.append(await lab.create_validation(c,sample,person['id'],person['id']))
            ready=asyncio.Event()
            arrivals=0
            class ShareConnection:
                """Faz dois responsáveis compartilharem tarefas distintas entre si."""
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
                    nonlocal arrivals
                    row=await self.c.fetchrow(sql,*args)
                    if 'SELECT u.id,u.name FROM users' in sql:
                        arrivals+=1
                        if arrivals==2:
                            ready.set()
                        await ready.wait()
                    return row
            async def share(index,actor,target):
                """Inclui o outro N1 como leitor de uma investigação independente nesta conexão.

                Args:
                    index: Índice da investigação independente usada no compartilhamento
                        concorrente.
                    actor: Registro do N1 responsável pela investigação deste competidor.
                    target: Registro da pessoa que receberá acesso de leitura à investigação.

                Returns:
                    ApiResponse[ValidationParticipantResponse]: Vínculo de leitura gravado e
                        auditado.

                Raises:
                    HTTPException: Quando a revalidação do fluxo recusa a credencial, o vínculo
                        ou o estado concorrente.
                """
                async with pool.acquire() as c:
                    return await add_participant(shared[index]['id'],ValidationParticipantAdd(user_id=target['id']),request,ShareConnection(c),actor)
            results=await asyncio.wait_for(asyncio.gather(share(0,owner,colleague),share(1,colleague,owner),return_exceptions=True),8)
            assert not any(isinstance(r,BaseException) for r in results),results
        finally:
            if pool:
                await pool.close()
            await control.execute('DROP SCHEMA '+schema+' CASCADE')
            await control.close()
    asyncio.run(scenario())
