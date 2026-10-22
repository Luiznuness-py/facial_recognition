"""Vínculos de role_permissions usados na consulta administrativa de papéis."""

from uuid import UUID

from schemas.sc_base_model import BaseSchema


class RolePermissionResponse(BaseSchema):
    """Identifica uma associação vigente entre papel e permissão.

    Representa a chave composta da tabela na montagem do catálogo de acesso.
    Não cria um endpoint de edição nem permite que o cliente conceda permissões.
    O serviço deve filtrar vínculos excluídos e consultar seus respectivos dados.

    Attributes:
        role_id: Papel ao qual a ação está associada.
        permission_id: Permissão concedida ao papel.
    """

    role_id: UUID
    permission_id: UUID
