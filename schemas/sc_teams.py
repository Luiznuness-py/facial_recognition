"""Projeção de teams para GET /teams e seleção de equipe."""

from uuid import UUID

from schemas.sc_base_model import BaseSchema


class TeamResponse(BaseSchema):
    """Apresenta a identificação administrativa de uma equipe.

    Serve à seleção de equipe e às referências em contas. O backend filtra
    equipes excluídas e verifica quais o usuário pode consultar.

    Attributes:
        id: Identificador da equipe.
        code: Código único do grupo.
        name: Nome apresentado na interface.
        description: Explicação opcional sobre a equipe.
    """

    id: UUID
    code: str
    name: str
    description: str | None = None
