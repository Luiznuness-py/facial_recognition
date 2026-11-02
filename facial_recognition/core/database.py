"""Pool PostgreSQL, migrations e reset do schema selecionado pelo ambiente."""
import logging
from pathlib import Path
from typing import Annotated
from collections.abc import AsyncIterator

from facial_recognition.core.settings import settings

import asyncpg
from fastapi import Request, Depends


async def get_connection(request: Request) -> AsyncIterator[asyncpg.Connection]:
    """Disponibiliza uma conexão do pool durante a requisição.

    Não abre uma transação automaticamente. A rota deve delimitá-la quando precisar de uma
    operação atômica.

    Args:
        request: Requisição cujo app.state contém o pool inicializado no lifespan.

    Yields:
        asyncpg.Connection: Conexão devolvida ao pool quando a dependência é encerrada.
    """
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        yield conn

Connection = Annotated[asyncpg.Connection, Depends(get_connection)]

async def create_pool() -> asyncpg.Pool:
    """Cria o pool PostgreSQL no banco DB_NAME e seleciona o schema do ambiente.

    Em test, cria o schema se necessário por uma conexão temporária. Não cria bancos nem
    executa migrations; API e pytest compartilham o mesmo banco do Docker.

    Returns:
        asyncpg.Pool: Pool com search_path=test em ENVIRONMENT=test e public nos demais
            ambientes.

    Raises:
        asyncpg.PostgresError: Quando o banco não existe, a conexão é recusada pelo
            PostgreSQL ou falta permissão para criar o schema.
        TimeoutError: Quando a conexão excede o prazo configurado.
    """
    schema = 'test' if settings.ENVIRONMENT == 'test' else 'public'
    dsn = settings.get_database_url()
    if schema == 'test':
        connection = await asyncpg.connect(dsn, timeout=10)
        try:
            await connection.execute('CREATE SCHEMA IF NOT EXISTS test')
        finally:
            await connection.close()
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=10,
        command_timeout=10,
        server_settings={'search_path': schema},
    )


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Aplica os arquivos SQL que ainda não constam em schema_migrations.

    Lê a pasta migrations do pacote em ordem de nome e executa a conferência e as alterações
    na mesma transação. Editar um arquivo já registrado não reaplica sua versão.

    Args:
        pool: Pool cujo search_path determina o schema que será atualizado.

    Returns:
        None: Registra no banco as versões aplicadas com sucesso.

    Raises:
        RuntimeError: Quando o banco registra uma migration ausente no código.
        OSError: Quando um arquivo SQL não pode ser lido.
        asyncpg.PostgresError: Quando a execução SQL falha; a transação é revertida.
    """
    migrations = Path(__file__).resolve().parents[1] / "migrations"

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

    logging.info("Migrations validadas ou criadas com sucesso!")


async def drop_all_tables(pool: asyncpg.Pool) -> None:
    """Recria o schema selecionado, removendo definitivamente suas tabelas e dados.

    Em test atua sobre test; em development atua sobre public. É uma ferramenta manual de
    reset, não o soft_delete do produto. O lifespan a chama no encerramento em test.

    Args:
        pool: Pool conectado ao banco que será afetado pelo reset.

    Returns:
        None: Recria o schema vazio dentro de uma transação.

    Raises:
        RuntimeError: Quando ENVIRONMENT não é development nem test.
        asyncpg.PostgresError: Quando o schema não pode ser removido ou recriado.
    """
    if settings.ENVIRONMENT not in {"development", "test"}:
        raise RuntimeError("Reset de banco permitido apenas em development ou test.")

    schema = "test" if settings.ENVIRONMENT == "test" else "public"

    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(f"DROP SCHEMA {schema} CASCADE")
            await connection.execute(f"CREATE SCHEMA {schema}")

    logging.info("Schema %s recriado sem tabelas.", schema)
