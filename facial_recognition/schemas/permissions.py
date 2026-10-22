"""Projeção do catálogo permissions para GET /admin/permissions e papéis."""

from uuid import UUID

from facial_recognition.schemas.base_model import BaseSchema


class PermissionResponse(BaseSchema):
    """Apresenta uma ação conhecida pelo controle de acesso.

    Usada na consulta administrativa e nas permissões de um papel. O serviço
    seleciona apenas permissões não excluídas; o schema não concede acesso.

    Attributes:
        id: Identificador da permissão no banco.
        code: Código que o backend verifica ao autorizar uma ação.
        description: Explicação da ação, quando cadastrada.
    """

    id: UUID
    code: str
    description: str | None = None
