"""Respostas de erro, instante UTC e auditoria transacional por requisição."""
from datetime import datetime, timezone

from fastapi.responses import JSONResponse


def failure(status, message, headers=None, *, request_id):
    """Monta o envelope HTTP padronizado para uma falha da API.

    Args:
        status: Código HTTP que será aplicado à resposta.
        message: Mensagem segura para apresentar ao consumidor.
        headers: Cabeçalhos opcionais, como Retry-After.
        request_id: UUID gerado pelo servidor para esta requisição.

    Returns:
        JSONResponse: Resposta com success=False, data=None e error.message.
    """
    return JSONResponse(
        status_code=status,
        content={
            'success': False,
            'data': None,
            'error': {
                'message': message,
                'details': {'request_id': str(request_id)}
                }
            },
            headers={**(headers or {}), "X-Request-ID": str(request_id)}
        )


def now():
    """Obtém o instante atual com fuso UTC explícito.

    Returns:
        datetime: Data e hora UTC para verificar prazos e criar expirações.
    """
    return datetime.now(timezone.utc)


async def audit(connection, actor, event, resource_type, target=None, success=True, *, request_id, reason=None):
    """Registra uma ação com autoria, tipo de recurso e resultado.

    Participa da transação do chamador e não abre uma transação própria. O request_id é
    compartilhado pelos eventos da mesma requisição HTTP.

    Args:
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        actor: UUID do autor ou None quando não houver usuário identificado.
        event: Código do evento que descreve a ação.
        resource_type: Tipo do recurso afetado, como users ou sessions.
        target: UUID do recurso afetado ou None quando não houver alvo específico.
        success: Indica se a ação registrada teve sucesso.
        request_id: UUID compartilhado pelos eventos desta requisição.
        reason: Motivo administrativo permitido; conteúdo científico reservado não é copiado.

    Returns:
        None: Insere uma linha em audit_events com o request_id recebido.
    """
    await connection.execute('INSERT INTO audit_events(actor_id,event,resource_type,resource_id,success,reason,request_id) VALUES($1,$2,$3,$4,$5,$6,$7)',
                             actor, event, resource_type, target, success, reason, request_id)
