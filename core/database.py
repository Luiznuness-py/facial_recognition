from pathlib import Path
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from core.settings import settings

import asyncpg
from fastapi import FastAPI, Request
from asyncpg import Connection, Pool


async def create_pool() -> Pool:
    """Cria o pool assíncrono de conexões com o PostgreSQL."""
    return await asyncpg.create_pool(
        dsn=settings.get_database_url(),
        min_size=1,
        max_size=10,
        command_timeout=10,
    )


async def get_connection(request: Request) -> AsyncIterator[Connection]:
    """Disponibiliza uma conexão do pool durante uma requisição FastAPI."""
    pool: Pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager # transforma uma função assíncrona com yield em um gerenciador de ciclo de vida
async def lifespan(app: FastAPI):
    """Aplica migrations ao iniciar a API e fecha o pool ao encerrá-la."""
    pool: Pool = await create_pool()

    try:
        await run_migrations(pool=pool)
        app.state.db_pool = pool
        yield
    finally:
        await pool.close()


async def run_migrations(pool: Pool) -> None:
    """Executa apenas os arquivos de migration ainda não registrados no banco."""
    migrations = Path("migrations")

    migration_files = sorted(migrations.glob("*.sql"))
    available_versions = {file.name for file in migration_files}

    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            applied_rows = await connection.fetch(
                "SELECT version FROM schema_migrations"
            )
            applied_versions = {row["version"] for row in applied_rows}

            unknown_versions = applied_versions - available_versions
            if unknown_versions:
                raise RuntimeError(
                    f"Banco possui migrations ausentes no código: "
                    f"{sorted(unknown_versions)}"
                )

            for migration_file in migration_files:
                if migration_file.name in applied_versions:
                    continue

                await connection.execute(
                    migration_file.read_text(encoding="utf-8")
                )
                await connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)",
                    migration_file.name,
                )


async def drop_all_tables(pool: Pool) -> None:
    """Remove o schema público em ambientes de desenvolvimento ou teste."""
    if settings.ENVIRONMENT not in {"development", "test"}:
        raise RuntimeError("Reset de banco permitido apenas em development ou test.")

    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("DROP SCHEMA public CASCADE")
            await connection.execute("CREATE SCHEMA public")
