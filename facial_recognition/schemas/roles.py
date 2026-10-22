"""Catálogo roles para GET /admin/roles e identificação de contas."""

from typing import Literal
from uuid import UUID

from facial_recognition.schemas.base_model import BaseSchema
from facial_recognition.schemas.permissions import PermissionResponse

RoleCode = Literal["ADMIN", "N1", "N2", "N3"]


class RoleResponse(BaseSchema):
    """Apresenta um papel e as ações vinculadas a ele.

    Usada no catálogo administrativo. As associações e permissões excluídas
    devem ser removidas pela consulta; esta resposta não substitui autorização.

    Attributes:
        id: Identificador do papel.
        code: Nível ADMIN, N1, N2 ou N3.
        name: Nome por extenso mostrado na interface.
        description: Descrição opcional do papel.
        permissions: Permissões vigentes selecionadas pelo serviço.
    """

    id: UUID
    code: RoleCode
    name: str
    description: str | None = None
    permissions: list[PermissionResponse]
