import logging
from contextlib import asynccontextmanager

from facial_recognition.settings import settings
from facial_recognition.schemas.base_model import ApiResponse
from facial_recognition.database import create_pool, run_migrations

from asyncpg import Pool
from fastapi import FastAPI


@asynccontextmanager # transforma uma função assíncrona com yield em um gerenciador de ciclo de vida
async def lifespan(app: FastAPI):
    """Aplica migrations ao iniciar a API e fecha o pool ao encerrá-la."""
    logging.info(
        "Starting %s v%s — env=%s debug=%s",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
        settings.DEBUG,
    )
    pool: Pool = await create_pool()

    try:
        await run_migrations(pool=pool)
        app.state.db_pool = pool
        yield
    finally:
        await pool.close()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


@app.get("/", response_model=ApiResponse[dict[str, str]], tags=["Root"])
async def root():
    return ApiResponse[dict[str, str]](
        data={
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }
    )


@app.get("/health", response_model=ApiResponse[dict[str, str]], tags=["Root"])
async def health_check():
    return ApiResponse[dict[str, str]](
        data={
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
