"""Orquestra os seeds na mesma transação a cada início da aplicação."""
from facial_recognition.seed.seed_admin import seed_admin
from facial_recognition.seed.seed_catalogs import seed_catalogs
from facial_recognition.core.settings import settings


async def run_seeds(connection, email: str | None = None, password: str | None = None):
    """Executa os seeds de catálogo e ADMIN na mesma transação.

    O advisory lock serializa inicializações concorrentes no banco. É chamado pelo lifespan
    a cada início e não deve ser confundido com reset ou recuperação de conta.

    Args:
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        email: Email opcional do ADMIN; None usa settings.ADMIN_EMAIL.
        password: Temporária opcional; None usa settings.ADMIN_SECRET.

    Returns:
        None: Confirma o bootstrap ou reverte as alterações se algum seed falhar.

    Raises:
        RuntimeError: Quando a configuração conflita com as contas ou os papéis existentes.
        HTTPException: Status 422 para uma nova temporária fora da política.
    """
    async with connection.transaction():
        await connection.execute('SELECT pg_advisory_xact_lock(827461)')
        await seed_catalogs(connection)
        await seed_admin(connection, email if email is not None else settings.ADMIN_EMAIL,
                         password if password is not None else settings.ADMIN_SECRET)
