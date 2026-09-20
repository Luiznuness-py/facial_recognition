import asyncio

from core.database import create_pool, run_migrations, drop_all_tables

async def main():
    """Executa as migrations e o reset de banco usado no teste manual atual."""

    pool = await create_pool()

    try:
        await run_migrations(pool=pool)
        await drop_all_tables(pool=pool)
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
