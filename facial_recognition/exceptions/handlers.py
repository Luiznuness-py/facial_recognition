"""Tratamento centralizado das exceções HTTP da API."""
import logging

from facial_recognition.utils.utils import failure


async def http_error(request, error):
    """Converte exceções HTTP do framework para o envelope da API.

    Args:
        request: Requisição associada; mantida na assinatura exigida pelo handler.
        error: Exceção com status_code, detail e cabeçalhos opcionais.

    Returns:
        JSONResponse: Falha padronizada com o status e os cabeçalhos originais.
    """
    return failure(error.status_code,error.detail,error.headers, request_id=request.state.request_id)


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
