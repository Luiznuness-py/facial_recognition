"""Schemas de access_requests para solicitar, consultar e decidir acesso."""

from uuid import UUID
from typing import Literal
from datetime import datetime

from facial_recognition.schemas.users import NewPassword, UserName
from facial_recognition.schemas.base_model import (
    BaseSchema, 
    PaginationParams, 
    NormalizedEmail, 
    Reason,
)

AccessRequestStatus = Literal["PENDING", "APPROVED", "REJECTED"]


class AccessRequestCreate(BaseSchema):
    """Recebe POST /access-requests, inclusive o cadastro direto pelo ADMIN.

    O cliente não informa autor, status ou identificador da conta. O backend
    deriva papel/equipe para N2/N3 e verifica o escopo das escolhas do ADMIN,
    unicidade e vagas. A senha é usada para gerar o hash, sem retorno ou log.

    Attributes:
        name, email: Identificação normalizada da pessoa solicitada.
        temporary_password: Senha temporária de 8 a 128 caracteres, sem strip.
        role_code, team_id: Escolhas opcionais, somente quando o ator puder fazê-las.
    """

    name: UserName
    email: NormalizedEmail
    temporary_password: NewPassword
    role_code: Literal["N1", "N2", "N3"] | None = None
    team_id: UUID | None = None


class AccessRequestResponse(BaseSchema):
    """Apresenta um pedido em criação, consulta, aprovação ou rejeição.

    Exclui a senha temporária e seu hash. A consulta deve respeitar solicitante
    e escopo administrativo e projetar somente estes campos.

    Attributes:
        id, user_id: Pedido e conta criada após aprovação, quando houver.
        requested_name, requested_email: Identificação da pessoa solicitada.
        requested_by, requested_role_id, requested_team_id: Autoria e acesso pedido.
        status, created_at: Situação e abertura da solicitação.
        decided_by, decided_at, rejection_reason: Metadados da decisão permitida.
    """

    id: UUID
    user_id: UUID | None = None
    requested_name: str
    requested_email: str
    requested_by: UUID
    requested_role_id: UUID
    requested_team_id: UUID | None = None
    status: AccessRequestStatus
    created_at: datetime
    decided_by: UUID | None = None
    decided_at: datetime | None = None
    rejection_reason: str | None = None


class AccessRequestReject(BaseSchema):
    """Recebe a justificativa de POST /access-requests/{id}/reject.

    O serviço verifica ADMIN e pedido pendente e remove o hash temporário ao
    decidir. O schema valida apenas o conteúdo permitido para essa ação.

    Attributes:
        reason: Motivo obrigatório de rejeição, até 1.500 caracteres.
    """

    reason: Reason


class AccessRequestQuery(PaginationParams):
    """Filtra GET /access-requests sem ampliar o escopo do solicitante.

    Herda page e per_page. O backend aplica autoria e exclusão lógica também
    ao total da listagem, sem permitir que o filtro contorne autorização.

    Attributes:
        status: Situação desejada; omitida, não restringe por decisão.
    """

    status: AccessRequestStatus | None = None
