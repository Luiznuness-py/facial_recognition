"""Entregas preservadas de investigation_submissions na consulta autorizada."""

from uuid import UUID
from decimal import Decimal
from datetime import datetime

from pydantic import Field

from facial_recognition.schemas.base_model import BaseSchema
from facial_recognition.schemas.validation_participants import ParticipantSnapshot


class InvestigationSubmissionResponse(BaseSchema):
    """Apresenta uma análise enviada e seus metadados de devolução.

    Usada dentro da leitura autorizada da investigação e do cofre. Não existe
    entrada de edição da entrega: o serviço cria a cópia ao enviar e preserva
    seu conteúdo. Uma correção produz outra entrega, sem sobrescrever esta.

    Attributes:
        id, validation_id, submission_number: Identificação e sequência do envio.
        responsible_user_id, submitted_by, submitted_at: Responsabilidade e autoria.
        assessments_performed, observed_results, technical_opinion, recommendation:
            Quatro textos científicos preservados na entrega.
        estimated_risk_percentage: Risco de 0 a 100, ou None se não determinado.
        participants_snapshot: Pessoas preservadas no momento do envio.
        returned_by, returned_at, return_reason: Devolução pelo N2, quando houver.
    """

    id: UUID
    validation_id: UUID
    submission_number: int = Field(gt=0)
    responsible_user_id: UUID
    submitted_by: UUID
    submitted_at: datetime
    assessments_performed: str = Field(min_length=1, max_length=1500)
    observed_results: str = Field(min_length=1, max_length=5000)
    technical_opinion: str = Field(min_length=1, max_length=5000)
    recommendation: str = Field(min_length=1, max_length=5000)
    estimated_risk_percentage: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    participants_snapshot: list[ParticipantSnapshot]
    returned_by: UUID | None = None
    returned_at: datetime | None = None
    return_reason: str | None = None
