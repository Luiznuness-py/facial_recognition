"""API e bancada temporária para testar o fluxo biométrico real."""
import asyncio
import logging
from uuid import uuid4
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from facial_recognition.routers import router
from facial_recognition.seed import run_seeds
from facial_recognition.utils.utils import failure
from facial_recognition.core.settings import settings
from facial_recognition.core.token_jwt import TokenJwt
from facial_recognition.core.inference import Inference
from facial_recognition.core.biometrics import FaceModels
from facial_recognition.core.security import hash_password
from facial_recognition.core.request_limit import RequestLimits
from facial_recognition.schemas.base_model import ApiResponse
from facial_recognition.core.database import (
    create_pool,
    run_migrations,
    drop_all_tables,
)


FRONTEND = Path(__file__).parent / 'frontend'


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa os recursos compartilhados da API e os encerra no desligamento.

    Em modo real, carrega os quatro modelos locais antes do banco, sem downloads.
    Em simulated, não carrega modelos e mantém somente as transições autenticadas.
    Executa o seed a cada início sem redefinir contas existentes. Ao encerrar, aguarda a
    tarefa de inferência iniciada e fecha o pool, inclusive quando a preparação do banco
    falha após sua criação.

    Args:
        app: Instância FastAPI que receberá tokens, inferência e pool em app.state.

    Yields:
        None: Entrega o controle ao servidor depois de migrations e seeds concluídos.

    Raises:
        ValueError: Quando SECRET_KEY não atende ao tamanho mínimo.
        RuntimeError: Quando os modelos locais não podem ser carregados ou migrations e
            bootstrap detectam um estado incompatível.
        asyncpg.PostgresError: Quando o banco não pode ser preparado.
    """
    app.state.tokens = TokenJwt()
    app.state.dummy_hash = await asyncio.to_thread(hash_password, 'invalid-credential-placeholder')
    inference = None
    if settings.BIOMETRICS_MODE == 'real':
        models = FaceModels()
        try:
            await asyncio.to_thread(models.load)
        except Exception as error:
            raise RuntimeError(
                'Modelos ausentes ou incompatíveis. Restaure os quatro arquivos '
                'de models/ a partir do repositório antes de iniciar a API. '
                'Consulte models/README.md para conferir os arquivos e suas origens.'
            ) from error
        inference = Inference(models)
    else:
        logging.warning('Biometria simulada ativa: nenhuma identidade facial será verificada.')
    app.state.inference = inference
    pool = await create_pool()
    try:
        await run_migrations(pool)
        async with pool.acquire() as connection:
            await run_seeds(connection)
        app.state.db_pool = pool
        yield
    finally:
        task = inference.task if inference is not None else None

        if task is not None:
            try:
                await asyncio.shield(task)
            except Exception:
                pass

        try:
            if settings.ENVIRONMENT == "test":
                await drop_all_tables(pool=pool)
        finally:
            await pool.close()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)
app.include_router(router)

app.mount(
    '/static',
    StaticFiles(directory=FRONTEND/'static'),
    name='static',
)

app.add_middleware(RequestLimits)

@app.get("/", response_model=ApiResponse[dict[str, str]], tags=["Root"])
async def root():
    """Apresenta a identificação pública da aplicação em GET /.

    Não acessa o banco nem informa credenciais da aplicação.

    Returns:
        ApiResponse[dict[str, str]]: Envelope com nome, versão e ambiente da aplicação.
    """
    return ApiResponse[dict[str, str]](
        data={
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }
    )


@app.get("/health", response_model=ApiResponse[dict[str, str]], tags=["Root"])
async def health_check():
    """Confirma que a camada HTTP está respondendo.

    Atende GET /health e apresenta a versão e o ambiente da aplicação. Não testa conexão
    com PostgreSQL, disponibilidade de pesos nem eficácia dos modelos.

    Returns:
        ApiResponse[dict[str, str]]: Envelope de sucesso com versão e ambiente da aplicação.
    """
    return ApiResponse[dict[str, str]](
        data={
            "status": "ok"
        }
    )


@app.middleware('http')
async def response_headers(request: Request, call_next):
    """Acrescenta os cabeçalhos de cache e proteção da interface.

    Gera request_id antes do limitador e o devolve no cabeçalho X-Request-ID.
    Autoriza câmera apenas na própria origem e restringe scripts, estilos e conexões a
    recursos locais. Não valida identidade ou permissões.

    Args:
        request: Requisição encaminhada para a aplicação.
        call_next: Função assíncrona que produz a resposta da rota.

    Returns:
        Response: Resposta com no-store, CSP, política de câmera e demais cabeçalhos
            definidos.
    """
    request.state.request_id = uuid4()
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request.state.request_id)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Permissions-Policy']='camera=(self), microphone=()'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request, error):
    """Converte exceções HTTP do framework para o envelope da API.

    Args:
        request: Requisição associada; mantida na assinatura exigida pelo handler.
        error: Exceção com status_code, detail e cabeçalhos opcionais.

    Returns:
        JSONResponse: Falha padronizada com o status e os cabeçalhos originais.
    """
    return failure(error.status_code,error.detail,error.headers, request_id=request.state.request_id)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    """Responde a falhas de validação sem devolver o conteúdo recebido.

    Não inclui input, senha ou o detalhamento bruto do Pydantic na resposta.

    Args:
        request: Requisição associada ao erro de validação.
        error: RequestValidationError recebido pelo FastAPI.

    Returns:
        JSONResponse: Envelope genérico com status 422.
    """
    return failure(422,'Confira os campos enviados e seus limites. Nenhum campo extra é permitido.', request_id=request.state.request_id)


@app.exception_handler(Exception)
async def unexpected_error(request, error):
    """Registra o tipo da falha inesperada e devolve uma mensagem genérica.

    O log contém somente caminho e nome da classe da exceção; não copia corpo da requisição,
    credenciais nem a mensagem interna da falha.

    Args:
        request: Requisição cujo caminho identifica a operação que falhou.
        error: Exceção não tratada por um handler mais específico.

    Returns:
        JSONResponse: Envelope de erro com status 500.
    """
    logging.error('Falha interna na operação %s (%s) request_id=%s',
                  request.url.path, type(error).__name__, request.state.request_id)
    return failure(500,'Não foi possível concluir a operação. Tente novamente.', request_id=request.state.request_id)
