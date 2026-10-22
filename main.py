import asyncio

from facial_recognition.log import configure_logging
from facial_recognition.database import create_pool, run_migrations, drop_all_tables

logger = configure_logging()

async def main():
    """Aplica as migrations sem remover os dados existentes."""

    pool = await create_pool()

    try:
        await run_migrations(pool=pool)
        # await drop_all_tables(pool=pool)
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
