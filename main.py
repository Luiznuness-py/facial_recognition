"""Comando manual de migrations sem iniciar servidor, seeds ou reset."""
import asyncio

from facial_recognition.core.log import configure_logging
from facial_recognition.core.database import create_pool, run_migrations, drop_all_tables

logger = configure_logging()

async def main():
    """Aplica migrations pelo comando manual e encerra o pool.

    Não inicia o servidor FastAPI nem executa os seeds do lifespan. Preserva os dados
    existentes e fecha o pool mesmo quando a migration falha.

    Returns:
        None: Termina depois de validar ou aplicar as versões pendentes.

    Raises:
        RuntimeError: Quando o histórico de migrations é incompatível.
        asyncpg.PostgresError: Quando a conexão ou a execução SQL falham.
    """

    pool = await create_pool()

    try:
        await run_migrations(pool=pool)
        # await drop_all_tables(pool=pool)
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
