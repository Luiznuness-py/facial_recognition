"""Envio ao N3, consultas do cofre vault e decisões sobre relatórios selados."""

from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field

from schemas.sc_publications import PublicRiskCategory
from schemas.sc_biological_agents import BiologicalAgentSummary
from schemas.sc_base_model import BaseSchema, PaginationParams, Reason
from schemas.sc_investigation_submissions import InvestigationSubmissionResponse

VaultDecisionStatus = Literal["WAITING_N3", "PUBLISHED", "RESTRICTED", "NEW_VALIDATION_REQUESTED"]
SentReportStatus = VaultDecisionStatus | Literal["WITHDRAWN"]


class VaultSend(BaseSchema):
    """Recebe POST /validations/{id}/report/send pelo N2.

    Exige relatório e ficha completos e normaliza as extremidades dos textos.
    O serviço verifica revisão e grupo, gera protocolo e cópia recebida e sela
    o conteúdo na mesma transação. O cliente não define autor, data ou decisão.

    Attributes:
        title: Título interno, até 120 caracteres.
        final_conclusion: Conclusão técnica não vazia, até 5.000 caracteres.
        final_risk_percentage: Risco final obrigatório, de 0 a 100 e duas casas.
        public_title, public_subtitle: Título até 120 e subtítulo opcional até 200.
        public_risk_category: Categoria pública escolhida, sem conversão automática.
        public_body: Notícia preparada, não vazia e com até 5.000 caracteres.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=120)
    final_conclusion: str = Field(min_length=1, max_length=5000)
    final_risk_percentage: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    public_title: str = Field(min_length=1, max_length=120)
    public_subtitle: str | None = Field(default=None, max_length=200)
    public_risk_category: PublicRiskCategory
    public_body: str = Field(min_length=1, max_length=5000)


class VaultSendResponse(BaseSchema):
    """Confirma o envio ao N3 sem devolver o conteúdo que acabou de ser selado.

    Usada pelo N2 após /report/send. O frontend pode acompanhar protocolo e
    situação, mas não deve manter uma cópia do formulário ministerial no navegador.

    Attributes:
        validation_id: Investigação encaminhada.
        status: REPORTED, mantendo a vaga ocupada até a decisão.
        protocol: Protocolo gerado pelo backend.
        sent_at: Momento em que o envio foi gravado.
    """

    validation_id: UUID
    status: Literal["REPORTED"]
    protocol: str
    sent_at: datetime


class NewValidationRequestResponse(BaseSchema):
    """Apresenta o pedido do N3 que a equipe autorizada pode acompanhar.

    Esta projeção compartilha apenas o pedido de nova investigação. Não inclui
    motivos de sigilo, retirada de notícia, conclusão ou snapshot do cofre.

    Attributes:
        reason: Motivo do pedido que pode ser comunicado ao N2 e à nova equipe.
        requested_at: Momento em que a autoridade solicitou outra tarefa.
        fulfilled_validation_id: Nova investigação criada para atender ao pedido.
    """

    reason: str
    requested_at: datetime
    fulfilled_validation_id: UUID | None = None


class SentReportResponse(BaseSchema):
    """Apresenta o card seguro de GET /reports/sent para o N2.

    Não contém relatório, ficha, risco interno nem motivos reservados. WITHDRAWN
    pode ser derivado da publicação para a situação exibida no card; isso não
    altera a decisão PUBLISHED preservada na tabela vault.

    Attributes:
        vault_id, validation_id: Identificadores do registro e da investigação.
        title, agent, protocol: Identificação mínima do envio acompanhado.
        decision_status: Situação exibida, incluindo notícia retirada.
        new_validation_request: Pedido compartilhável do N3, quando houver.
    """

    vault_id: UUID
    validation_id: UUID
    title: str
    agent: BiologicalAgentSummary
    protocol: str
    decision_status: SentReportStatus
    new_validation_request: NewValidationRequestResponse | None = None


class VaultSummary(BaseSchema):
    """Apresenta um registro na listagem privada GET /vault/dossiers.

    O nome HTTP dossiers representa os relatórios dentro do cofre; a tabela se
    chama vault. O backend exige N3 e aplica os filtros e a exclusão lógica.

    Attributes:
        id, validation_id: Identificadores do registro e da investigação.
        title, agent, protocol: Identificação do relatório e da amostra.
        decision_status: Decisão registrada no cofre.
        sent_at: Momento do envio ao N3.
    """

    id: UUID
    validation_id: UUID
    title: str
    agent: BiologicalAgentSummary
    protocol: str
    decision_status: VaultDecisionStatus
    sent_at: datetime


class VaultResponse(VaultSummary):
    """Apresenta o conteúdo completo de GET /vault/dossiers/{id}, exclusivo N3.

    Herda a identificação do resumo e inclui relatório, ficha, entrega e cópia
    recebida. Não deve ser reutilizada em cards N2, consultas N1 ou publicação
    pública. O serviço seleciona o snapshot histórico sem credenciais.

    Attributes:
        source_submission_id, submission: Entrega preservada que originou o cofre.
        sent_by, received_snapshot: Autor do envio e cópia recebida em JSON.
        final_conclusion, final_risk_percentage: Conclusão e risco consolidados.
        public_title, public_subtitle, public_risk_category, public_body: Ficha selada.
        decided_by, decided_at, restricted_reason: Decisão e motivo exclusivo N3.
        new_validation_requested_by, new_validation_requested_at,
        new_validation_request_reason, request_fulfilled_by_validation_id:
            Autoria, momento, motivo e atendimento do pedido de outra tarefa.
    """

    source_submission_id: UUID
    submission: InvestigationSubmissionResponse
    sent_by: UUID
    received_snapshot: dict[str, Any]
    final_conclusion: str
    final_risk_percentage: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    public_title: str
    public_subtitle: str | None = None
    public_risk_category: PublicRiskCategory
    public_body: str
    decided_by: UUID | None = None
    decided_at: datetime | None = None
    restricted_reason: str | None = None
    new_validation_requested_by: UUID | None = None
    new_validation_requested_at: datetime | None = None
    new_validation_request_reason: str | None = None
    request_fulfilled_by_validation_id: UUID | None = None


class VaultDecisionReason(BaseSchema):
    """Recebe o motivo das decisões /keep-restricted e /request-validation.

    Ambas exigem N3 e relatório aguardando decisão. O serviço distingue os
    destinos: sigilo guarda motivo exclusivo N3; nova investigação compartilha
    somente o pedido com a equipe autorizada. Nenhuma ação edita o relatório.

    Attributes:
        reason: Justificativa não vazia, com até 1.500 caracteres.
    """

    reason: Reason


class VaultDecisionResponse(BaseSchema):
    """Confirma sigilo ou pedido de outra investigação, sem expor motivos.

    O serviço grava a decisão terminal e encerra a investigação anterior em
    transação. Publicar usa a resposta de publicação, pois cria a cópia pública.

    Attributes:
        vault_id: Registro do cofre decidido pelo N3.
        decision_status: RESTRICTED ou NEW_VALIDATION_REQUESTED.
        validation_id: Investigação encerrada pela decisão.
        status: Estado CLOSED da investigação anterior.
    """

    vault_id: UUID
    decision_status: Literal["RESTRICTED", "NEW_VALIDATION_REQUESTED"]
    validation_id: UUID
    status: Literal["CLOSED"]


class VaultQuery(PaginationParams):
    """Filtra os registros da listagem privada do cofre.

    Herda page e per_page. A existência de filtros não concede acesso ao N2 ou
    ADMIN; o serviço exige N3 e usa parâmetros SQL para os valores recebidos.

    Attributes:
        protocol: Protocolo opcional para localizar um relatório.
        decision_status: Situação opcional da decisão preservada no cofre.
    """

    protocol: str | None = None
    decision_status: VaultDecisionStatus | None = None


class SentReportQuery(PaginationParams):
    """Filtra GET /reports/sent sem conceder leitura do cofre ao N2.

    Herda page e per_page. O serviço restringe ao grupo do N2 e pode derivar
    WITHDRAWN da publicação para atender ao filtro de notícias retiradas.

    Attributes:
        search: Busca opcional pela identificação do relatório.
        decision_status: Situação exibida no card, quando informada.
    """

    search: str | None = None
    decision_status: SentReportStatus | None = None
