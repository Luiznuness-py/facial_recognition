"""Formulário, ações e projeções de validations, sem conteúdo ministerial."""

from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from schemas.sc_vault import NewValidationRequestResponse
from schemas.sc_users import UserSummary
from schemas.sc_biological_agents import BiologicalAgentSummary
from schemas.sc_validation_participants import ValidationParticipantResponse
from schemas.sc_investigation_submissions import InvestigationSubmissionResponse
from schemas.sc_base_model import AuditSchema, BaseSchema, PaginationParams, Reason

ValidationStatus = Literal["OPEN", "IN_REVIEW", "RETURNED", "REPORTED", "PUBLISHED", "CLOSED"]
ClosureCause = Literal["N2_CLOSED", "N3_RESTRICTED", "N3_NEW_VALIDATION"]


class ValidationCreate(BaseSchema):
    """Recebe POST /biological-agents/{id}/validations.

    O serviço exige N2 do grupo, amostra ativa e vaga, atribui o N1 e confere
    eventual pedido do N3. Não recebe equipe, autor, estado ou identificador novo.

    Attributes:
        responsible_user_id: N1 escolhido para editar e enviar a investigação.
        request_vault_id: Registro do cofre cujo pedido será atendido, se houver.
    """

    responsible_user_id: UUID
    request_vault_id: UUID | None = None


class ValidationAnalysisUpdate(BaseSchema):
    """Recebe o rascunho parcial em PATCH /validations/{id}/analysis.

    Aceita textos incompletos e null para limpar campos do rascunho. Omitir
    preserva o valor; use model_dump(exclude_unset=True). O serviço verifica o
    responsável e OPEN/RETURNED e exige os textos completos somente no envio.

    Attributes:
        assessments_performed: Avaliações com até 1.500 caracteres.
        observed_results, technical_opinion, recommendation: Textos até 5.000.
        estimated_risk_percentage: Percentual de 0 a 100 com até duas casas,
            ou null para risco não determinado. Zero é um valor válido.
    """

    assessments_performed: str | None = Field(default=None, max_length=1500)
    observed_results: str | None = Field(default=None, max_length=5000)
    technical_opinion: str | None = Field(default=None, max_length=5000)
    recommendation: str | None = Field(default=None, max_length=5000)
    estimated_risk_percentage: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        """Rejeita um PATCH sem campos, mantendo a distinção entre omissão e null."""
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para alterar.")
        return self


class ValidationResponsibleUpdate(BaseSchema):
    """Recebe PATCH /validations/{id}/responsible.

    O serviço exige N2, tarefa editável e N1 ativo do grupo. A troca preserva
    as entregas, ajusta vínculos de leitura e registra as ações em transação.

    Attributes:
        responsible_user_id: Identificador do novo responsável pela investigação.
    """

    responsible_user_id: UUID


class ValidationReturn(BaseSchema):
    """Recebe o motivo de POST /validations/{id}/return.

    A devolução é permitida somente ao N2 do grupo na revisão. O backend
    registra autor/data na entrega e retorna a investigação ao responsável.

    Attributes:
        reason: Orientação obrigatória de correção, até 1.500 caracteres.
    """

    reason: Reason


class ValidationClose(BaseSchema):
    """Recebe o encerramento manual de POST /validations/{id}/close.

    O serviço exige N2 do grupo e IN_REVIEW e define causa N2_CLOSED. Motivos
    ministeriais não são recebidos aqui nem copiados para a justificativa N2.

    Attributes:
        reason: Justificativa obrigatória de encerramento, até 1.500 caracteres.
    """

    reason: Reason


class ValidationCardResponse(BaseSchema):
    """Apresenta um card autorizado de investigação.

    Expõe a identificação e orientações de interface, sem conteúdo do cofre.
    can_edit e can_submit não substituem as verificações de cada ação no backend.

    Attributes:
        id, status: Identificação e situação da investigação.
        responsible: Identificação mínima do responsável atual.
        created_at, latest_submitted_at: Abertura e envio mais recente, se houver.
        can_edit, can_submit: Indicações de ações disponíveis na interface.
        closure_reason, return_reason: Motivos autorizados de encerramento N2
            e da devolução mais recente.
        new_validation_request: Pedido N3 autorizado à equipe, quando houver.
    """

    id: UUID
    status: ValidationStatus
    responsible: UserSummary
    created_at: datetime
    latest_submitted_at: datetime | None = None
    can_edit: bool
    can_submit: bool
    closure_reason: str | None = None
    return_reason: str | None = None
    new_validation_request: NewValidationRequestResponse | None = None


class ValidationResponse(AuditSchema):
    """Apresenta a investigação e suas entregas a usuários autorizados.

    Herda os campos comuns de auditoria. O serviço aplica grupo e vínculo atual
    e seleciona entregas permitidas. Não inclui ficha ministerial, conclusão N2,
    snapshot do cofre nem motivos reservados ao N3.

    Attributes:
        id, agent, team_id, status: Identificação e situação da tarefa.
        responsible, participants: Responsável atual e colaboradores vigentes.
        assessments_performed, observed_results, technical_opinion, recommendation:
            Formulário atual, permitindo campos incompletos de rascunho.
        estimated_risk_percentage: Risco opcional entre 0 e 100.
        submissions: Entregas históricas autorizadas.
        closed_at, closed_by, closure_reason, closure_cause: Encerramento permitido,
            com justificativa apenas do N2.
        previous_validation_id: Investigação anterior quando atende pedido N3.
        new_validation_request: Pedido N3 autorizado à equipe, quando houver.
    """

    id: UUID
    agent: BiologicalAgentSummary
    team_id: UUID
    status: ValidationStatus
    responsible: UserSummary
    participants: list[ValidationParticipantResponse]
    assessments_performed: str | None = None
    observed_results: str | None = None
    technical_opinion: str | None = None
    recommendation: str | None = None
    estimated_risk_percentage: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    submissions: list[InvestigationSubmissionResponse]
    closed_at: datetime | None = None
    closed_by: UUID | None = None
    closure_reason: str | None = None
    closure_cause: ClosureCause | None = None
    previous_validation_id: UUID | None = None
    new_validation_request: NewValidationRequestResponse | None = None


class ValidationSubmitResponse(BaseSchema):
    """Confirma POST /validations/{id}/submit sem reenviar toda a entrega.

    O serviço preserva o formulário e participantes e impede envios duplicados.
    Autor e momento vêm da operação efetivamente gravada no banco.

    Attributes:
        id: Identificador da investigação enviada.
        status: IN_REVIEW, indicando análise entregue ao N2.
        submitted_at: Momento do envio preservado.
    """

    id: UUID
    status: Literal["IN_REVIEW"]
    submitted_at: datetime


class ValidationReturnResponse(BaseSchema):
    """Confirma a devolução e apresenta o motivo compartilhado à equipe.

    Os dados são extraídos da devolução registrada, sem modificar a análise
    entregue. O backend confere quem pode ler a investigação e esse motivo.

    Attributes:
        id: Investigação devolvida.
        status: RETURNED, permitindo ao responsável voltar a editar.
        reason, returned_at: Justificativa e momento da devolução.
    """

    id: UUID
    status: Literal["RETURNED"]
    reason: str
    returned_at: datetime


class ValidationCloseResponse(BaseSchema):
    """Confirma o encerramento manual pelo N2.

    Representa apenas a ação /close, não decisões reservadas do cofre. Seus
    metadados são definidos pelo backend e não por campos recebidos do cliente.

    Attributes:
        id, status: Investigação e estado CLOSED.
        closed_by, closed_at: Autor e momento do encerramento.
        closure_reason: Justificativa compartilhada pelo N2.
        closure_cause: Causa fixa N2_CLOSED para esta operação.
    """

    id: UUID
    status: Literal["CLOSED"]
    closed_by: UUID
    closed_at: datetime
    closure_reason: str
    closure_cause: Literal["N2_CLOSED"]


class ValidationQuery(PaginationParams):
    """Filtra cards de GET /biological-agents/{id}/validations.

    Herda page e per_page. O backend aplica o mesmo escopo aos itens e ao total,
    sem liberar outras investigações somente por pertencerem à mesma amostra.

    Attributes:
        status: Situação opcional da investigação.
    """

    status: ValidationStatus | None = None


class ValidationCreatedResponse(BaseSchema):
    """Confirma uma investigação criada pelo N2, inclusive por pedido N3.

    Attributes:
        id, status: Identificador e estado inicial OPEN da nova investigação.
        responsible_user_id: N1 atribuído à tarefa.
        new_validation_request: Pedido autorizado atendido, quando houver.
    """

    id: UUID
    status: Literal["OPEN"]
    responsible_user_id: UUID
    new_validation_request: NewValidationRequestResponse | None = None


class ValidationResponsibleResponse(BaseSchema):
    """Apresenta os vínculos vigentes após substituir o responsável.

    Attributes:
        responsible: Identificação mínima do novo responsável.
        participants: Colaboradores em leitura mantidos após a troca.
    """

    responsible: UserSummary
    participants: list[ValidationParticipantResponse]
