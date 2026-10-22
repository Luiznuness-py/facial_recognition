"""Projeções privada e pública de publications e ação de retirada."""

from uuid import UUID
from typing import Literal
from datetime import datetime

from facial_recognition.schemas.base_model import BaseSchema, PaginationParams, Reason

PublicRiskCategory = Literal["LOW", "MODERATE", "HIGH"]
PublicationStatus = Literal["PUBLISHED", "WITHDRAWN"]


class PublicPublicationResponse(BaseSchema):
    """Apresenta somente a ficha aprovada nas rotas /public/publications.

    O backend projeta public_title, public_subtitle, public_risk_category e
    public_body nos nomes abaixo e seleciona apenas notícias publicadas e não
    excluídas. Não inclui vínculo ao cofre, equipe, local exato ou motivo de retirada.

    Attributes:
        id: Identificador público da notícia.
        title, subtitle: Título e subtítulo opcional aprovados.
        risk_category: Categoria pública de risco.
        body: Texto público aprovado pelo N3.
        published_at: Momento da publicação.
    """

    id: UUID
    title: str
    subtitle: str | None = None
    risk_category: PublicRiskCategory
    body: str
    published_at: datetime


class PublicationResponse(PublicPublicationResponse):
    """Acrescenta os metadados privados para a gestão de notícias pelo N3.

    Usada nas rotas privadas /publications, nunca nas rotas públicas. Herda a
    ficha divulgável e adiciona o vínculo interno e a retirada reservada.

    Attributes:
        vault_id: Registro do cofre que originou a notícia.
        status: Situação publicada ou retirada.
        published_by: N3 que aprovou a divulgação.
        withdrawn_by, withdrawn_at: Autor e momento da retirada, quando houver.
        withdrawal_reason: Justificativa reservada ao N3.
    """

    vault_id: UUID
    status: PublicationStatus
    published_by: UUID
    withdrawn_by: UUID | None = None
    withdrawn_at: datetime | None = None
    withdrawal_reason: str | None = None


class PublicationWithdraw(BaseSchema):
    """Recebe o motivo de POST /publications/{id}/withdraw.

    O serviço exige N3 e preserva conteúdo, autoria e decisão original. O motivo
    não pode ser copiado para respostas públicas ou auditoria administrativa.

    Attributes:
        reason: Justificativa não vazia, com até 1.500 caracteres.
    """

    reason: Reason


class PublicationPublishResponse(BaseSchema):
    """Confirma a publicação aprovada em POST /vault/dossiers/{id}/publish.

    Informa o identificador público e o momento da divulgação sem reenviar o
    conteúdo selado. O serviço mantém a operação idempotente e a cópia aprovada.

    Attributes:
        id: Identificador da notícia criada ou já publicada.
        status: Estado PUBLISHED da publicação.
        published_at: Momento original da publicação preservada.
    """

    id: UUID
    status: Literal["PUBLISHED"]
    published_at: datetime


class PublicationWithdrawResponse(BaseSchema):
    """Confirma POST /publications/{id}/withdraw sem repetir o motivo reservado.

    Repetir a ação retorna o momento de retirada já registrado, sem substituir
    motivo ou autoria. O serviço preserva o conteúdo e não reabre a investigação.

    Attributes:
        id: Identificador da notícia retirada.
        status: Estado WITHDRAWN da publicação.
        withdrawn_at: Momento da retirada preservado pelo backend.
    """

    id: UUID
    status: Literal["WITHDRAWN"]
    withdrawn_at: datetime


class PublicPublicationQuery(PaginationParams):
    """Recebe a busca pública de notícias sem permitir seleção de retiradas.

    Herda page e per_page. O backend fixa PUBLISHED e soft_delete=FALSE na
    consulta e no total, independentemente do texto pesquisado.

    Attributes:
        search: Texto opcional de busca no conteúdo público aprovado.
    """

    search: str | None = None


class PublicationQuery(PublicPublicationQuery):
    """Filtra a listagem privada de publicações do N3.

    Acrescenta a situação à paginação e pesquisa herdadas. Consultar retiradas
    não transforma esta consulta em pública nem permite republicar uma notícia.

    Attributes:
        status: Situação opcional PUBLISHED ou WITHDRAWN.
    """

    status: PublicationStatus | None = None
