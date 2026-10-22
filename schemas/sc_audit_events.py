"""Consulta sanitizada de audit_events; eventos são escritos pelo backend."""

from uuid import UUID
from typing import Self
from datetime import datetime

from pydantic import model_validator

from schemas.sc_base_model import BaseSchema, PaginationParams


class AuditEventResponse(BaseSchema):
    """Apresenta um evento permitido em GET /admin/audit-events.

    A projeção administrativa não pode incluir conteúdo científico, senhas,
    tokens, embeddings ou motivos reservados ao N3. Filtrar e sanitizar esses
    eventos é responsabilidade do serviço, antes da construção da resposta.

    Attributes:
        id, actor_id: Evento e usuário identificado, quando houver.
        event, resource_type, resource_id: Ação e recurso afetado.
        success, reason: Resultado e motivo que o administrador pode consultar.
        request_id, created_at: Correlação e momento da requisição.
    """

    id: UUID
    actor_id: UUID | None = None
    event: str
    resource_type: str
    resource_id: UUID | None = None
    success: bool
    reason: str | None = None
    request_id: UUID
    created_at: datetime


class AuditEventQuery(PaginationParams):
    """Filtra eventos administrativos por ação, usuário e período.

    Herda page e per_page e rejeita períodos invertidos. A comparação pressupõe
    datas com fuso, para não misturar instantes locais e UTC na consulta.

    Attributes:
        event: Código opcional da ação.
        actor_id: Autor identificado a pesquisar.
        date_from, date_to: Limites inclusivos do período consultado.
    """

    event: str | None = None
    actor_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        """Exige fuso nos instantes enviados e início não posterior ao fim."""
        for instant in (self.date_from, self.date_to):
            if instant is not None and instant.utcoffset() is None:
                raise ValueError("Informe o fuso horário nas datas do período.")
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("O início do período não pode ser posterior ao fim.")
        return self
