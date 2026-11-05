"""Carga manual de dados fictícios; execute somente em development/simulated."""
import asyncio
from uuid import uuid4

from facial_recognition.core.accounts import check_position, password_hash, set_temporary_password
from facial_recognition.core.database import create_pool, run_migrations
from facial_recognition.core.settings import settings
from facial_recognition.seed import run_seeds
from pydantic import SecretStr

TEMPORARY_PASSWORD = 'Temporary!Demo2026'


async def seed_development(connection):
    """Insere contas fictícias sem redefinir credenciais ou posições existentes.

    Deve ser chamada em transação pelo comando local ou fixture isolado. Insere seis contas
    fictícias e uma amostra; não redefine contas existentes nem corrige seus papéis/equipes.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.

    Returns:
        None: Carga preparada com contas novas pendentes de ativação.

    Raises:
        HTTPException: Status 409 para vaga N2/N3 ocupada; 422 para configuração de papel/equipe
            ou senha inválidos.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    admin = await connection.fetchval("SELECT u.id FROM users u JOIN roles r ON r.id=u.role_id WHERE r.code='ADMIN' AND NOT u.soft_delete AND NOT r.soft_delete")
    encoded = await password_hash(SecretStr(TEMPORARY_PASSWORD))
    for name, email, role_code, team_code in [
        ('N1 Equipe A','n1.a@example.com','N1','A'),
        ('N1 Colaborador A','colaborador.a@example.com','N1','A'),
        ('N2 Equipe A','n2.a@example.com','N2','A'),
        ('N1 Equipe B','n1.b@example.com','N1','B'),
        ('N2 Equipe B','n2.b@example.com','N2','B'),
        ('Autoridade N3','n3@example.com','N3',None),
    ]:
        if await connection.fetchval('SELECT EXISTS(SELECT 1 FROM users WHERE email=$1)',email):
            continue
        team = await connection.fetchval('SELECT id FROM teams WHERE code=$1 AND NOT soft_delete',team_code) if team_code else None
        role = await check_position(connection,role_code,team)
        id = await connection.fetchval('INSERT INTO users(name,email,role_id,team_id,created_by) VALUES($1,$2,$3,$4,$5) RETURNING id',name,email,role,team,admin)
        await set_temporary_password(connection,id,encoded,admin)
    owner=await connection.fetchrow("SELECT id,team_id FROM users WHERE email='n1.a@example.com' AND NOT soft_delete")
    if owner and not await connection.fetchval('SELECT EXISTS(SELECT 1 FROM biological_agents WHERE created_by=$1)',owner['id']):
        agent_id=await connection.fetchval('''INSERT INTO biological_agents(code,provisional_label,material_type,collection_location,collected_on,
            initial_observations,investigation_reason,team_id,created_by)
            VALUES($1,'Amostra fictícia de água','Água','Local fictício',CURRENT_DATE,'Dados fictícios','Exercício acadêmico',$2,$3) RETURNING id''', 'DEMO-'+uuid4().hex,owner['team_id'],owner['id'])
        await connection.execute('INSERT INTO validations(agent_id,team_id,responsible_user_id,created_by) VALUES($1,$2,$3,$3)',agent_id,owner['team_id'],owner['id'])


async def main():
    """Aplica carga explicitamente local em transação, preservando dados preexistentes.

    Exige development/simulated antes de conectar. Aplica migrations, bootstrap e carga fictícia
    transacional, fechando o pool em finally sem apagar dados existentes.

    Returns:
        None: Encerra após preparar a carga local.

    Raises:
        RuntimeError: Para ambiente/modo proibidos ou histórico de migrations incompatível.
        HTTPException: Quando vaga ou dados da carga impedem sua criação.
        asyncpg.PostgresError: Quando o PostgreSQL não pode executar a preparação.
    """
    if settings.ENVIRONMENT!='development' or settings.BIOMETRICS_MODE!='simulated':
        raise RuntimeError('Carga fictícia exige ENVIRONMENT=development e BIOMETRICS_MODE=simulated.')
    pool=await create_pool()
    try:
        await run_migrations(pool)
        async with pool.acquire() as connection:
            async with connection.transaction():
                await run_seeds(connection)
                await seed_development(connection)
    finally:
        await pool.close()


if __name__=='__main__':
    asyncio.run(main())
