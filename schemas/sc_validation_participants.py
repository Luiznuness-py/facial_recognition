"""Compartilhamento de leitura e projeções de validation_participants."""

from datetime import datetime
from uuid import UUID

from schemas.sc_roles import RoleCode
from schemas.sc_base_model import BaseSchema


class ValidationParticipantAdd(BaseSchema):
    """Recebe POST /validations/{id}/participants.

    O identificador da investigação vem do caminho, e autor/data vêm da sessão.
    O serviço verifica N1 ativo do mesmo grupo, estado OPEN/RETURNED e restaura
    o vínculo existente quando apropriado, sem conceder edição.

    Attributes:
        user_id: Identificador do colaborador convidado para leitura.
    """

    user_id: UUID


class ValidationParticipantResponse(BaseSchema):
    """Apresenta um colaborador vigente nas consultas da investigação.

    Não expõe email nem credenciais. Remoção usa exclusão lógica no serviço;
    a resposta deve ser construída somente com vínculos atualmente autorizados.

    Attributes:
        user_id, name: Identificação do colaborador.
        added_by, added_at: Autor e momento da inclusão original.
    """

    user_id: UUID
    name: str
    added_by: UUID
    added_at: datetime


class ParticipantSnapshot(BaseSchema):
    """Representa uma pessoa na cópia histórica de uma entrega.

    Diferentemente do vínculo atual, preserva a identificação daquele momento.
    Não concede acesso posterior nem inclui senha, email ou representação facial.

    Attributes:
        user_id: Identificador preservado da pessoa.
        name: Nome no momento do envio.
        role_code: Papel registrado no momento da entrega.
    """

    user_id: UUID
    name: str
    role_code: RoleCode
