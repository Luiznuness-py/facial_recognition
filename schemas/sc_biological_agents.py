"""Entradas e projeções de biological_agents nas rotas de amostras."""

from uuid import UUID
from typing import Literal, Self
from datetime import date, datetime

from pydantic import ConfigDict, Field, field_validator, model_validator

from schemas.sc_base_model import AuditSchema, BaseSchema, PaginationParams

AgentStatus = Literal["ACTIVE", "INACTIVE"]


class BiologicalAgentCreate(BaseSchema):
    """Recebe o cadastro de POST /biological-agents.

    Normaliza as extremidades dos textos e valida os limites cadastrais. Código,
    equipe, autoria, estado e primeira investigação são definidos pelo serviço,
    que verifica N1 e cria os registros na mesma transação.

    Attributes:
        provisional_label: Identificação provisória, até 120 caracteres.
        material_type: Material coletado, até 100 caracteres.
        collection_location: Local da coleta, até 255 caracteres.
        collected_on: Dia da coleta, sem permitir data futura no servidor.
        initial_observations, investigation_reason: Textos obrigatórios até 1.500.
        known_information: Informação complementar opcional, até 1.500.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    provisional_label: str = Field(min_length=1, max_length=120)
    material_type: str = Field(min_length=1, max_length=100)
    collection_location: str = Field(min_length=1, max_length=255)
    collected_on: date
    initial_observations: str = Field(min_length=1, max_length=1500)
    investigation_reason: str = Field(min_length=1, max_length=1500)
    known_information: str | None = Field(default=None, max_length=1500)

    @field_validator("collected_on")
    @classmethod
    def validate_collection_date(cls, value: date) -> date:
        """Rejeita coleta posterior à data atual do servidor."""
        if value > date.today():
            raise ValueError("A data da coleta não pode estar no futuro.")
        return value


class BiologicalAgentUpdate(BaseSchema):
    """Recebe a correção parcial de PATCH /biological-agents/{id}.

    Omitir um campo preserva seu valor; apenas known_information aceita null
    explícito. Use model_dump(exclude_unset=True). O serviço verifica vínculo,
    grupo e ausência da primeira entrega antes de permitir alterações.

    Attributes:
        provisional_label, material_type, collection_location: Textos cadastrais
            opcionais na requisição, com os mesmos limites da criação.
        collected_on: Nova data de coleta, sem permitir data futura.
        initial_observations, investigation_reason: Textos até 1.500 caracteres.
        known_information: Complemento até 1.500, ou null para limpar o campo.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    provisional_label: str | None = Field(default=None, min_length=1, max_length=120)
    material_type: str | None = Field(default=None, min_length=1, max_length=100)
    collection_location: str | None = Field(default=None, min_length=1, max_length=255)
    collected_on: date | None = None
    initial_observations: str | None = Field(default=None, min_length=1, max_length=1500)
    investigation_reason: str | None = Field(default=None, min_length=1, max_length=1500)
    known_information: str | None = Field(default=None, max_length=1500)

    @field_validator("collected_on")
    @classmethod
    def validate_collection_date(cls, value: date | None) -> date | None:
        """Rejeita data futura; null explícito é tratado na validação do PATCH."""
        if value is not None and value > date.today():
            raise ValueError("A data da coleta não pode estar no futuro.")
        return value

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        """Exige alteração e permite limpar apenas a informação complementar."""
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para alterar.")
        for field in self.model_fields_set - {"known_information"}:
            if getattr(self, field) is None:
                raise ValueError(f"O campo {field} não aceita null.")
        return self


class BiologicalAgentStatusUpdate(BaseSchema):
    """Recebe a situação científica em PATCH /biological-agents/{id}/status.

    Não recebe soft_delete: inativação científica é uma decisão diferente da
    exclusão lógica. O serviço exige N2 do grupo e ausência de tarefa em andamento.

    Attributes:
        status: ACTIVE para permitir novas investigações ou INACTIVE para inativar.
    """

    status: AgentStatus


class BiologicalAgentSummary(BaseSchema):
    """Identifica a amostra em cards de investigação e relatórios.

    Mantém somente os campos necessários à identificação. Não concede acesso
    a outras investigações, ao local da coleta nem ao conteúdo do cofre.

    Attributes:
        id: Identificador da amostra.
        code: Código único do cadastro.
        provisional_label: Identificação provisória da amostra.
    """

    id: UUID
    code: str
    provisional_label: str


class BiologicalAgentResponse(AuditSchema):
    """Apresenta o cadastro completo autorizado, sem incluir todas as análises.

    Usada nas consultas e correções de amostras. Herda datas, autores e exclusão
    lógica de AuditSchema. O backend aplica os mesmos vínculos na lista e detalhe.

    Attributes:
        id, code, provisional_label: Identificação da amostra.
        material_type, collection_location, collected_on: Dados da coleta.
        initial_observations, investigation_reason, known_information: Cadastro.
        team_id: Equipe à qual a amostra pertence.
        status: Situação científica ACTIVE ou INACTIVE.
    """

    id: UUID
    code: str
    provisional_label: str
    material_type: str
    collection_location: str
    collected_on: date
    initial_observations: str
    investigation_reason: str
    known_information: str | None = None
    team_id: UUID
    status: AgentStatus


class CreatedAgentResponse(BiologicalAgentSummary):
    """Apresenta a projeção mínima da amostra recém-criada.

    Complementa a identificação herdada para o retorno de POST /biological-agents.
    Equipe, situação e data vêm dos registros produzidos pelo backend.

    Attributes:
        status: Estado inicial ativo da amostra.
        team_id: Equipe atribuída ao cadastro.
        created_at: Momento de criação.
    """

    status: Literal["ACTIVE"]
    team_id: UUID
    created_at: datetime


class InitialValidationResponse(BaseSchema):
    """Identifica a investigação criada junto da primeira amostra.

    É a parte validation da resposta de cadastro, não um formulário editável.
    A criação atômica e a atribuição ao N1 criador são garantidas pelo serviço.

    Attributes:
        id: Identificador da primeira investigação.
        status: Estado inicial OPEN.
        responsible_user_id: N1 responsável definido pelo backend.
    """

    id: UUID
    status: Literal["OPEN"]
    responsible_user_id: UUID


class BiologicalAgentCreateResponse(BaseSchema):
    """Agrupa o resultado atômico de POST /biological-agents.

    Mostra os dois identificadores necessários para abrir o cadastro e sua
    primeira tarefa. Não inclui conteúdo de análises nem dados de outros grupos.

    Attributes:
        agent: Identificação da amostra criada.
        validation: Identificação da primeira investigação atribuída ao criador.
    """

    agent: CreatedAgentResponse
    validation: InitialValidationResponse


class BiologicalAgentQuery(PaginationParams):
    """Define busca e situação na listagem autorizada de amostras.

    Herda page e per_page. A consulta aplica escopo e exclusão lógica também
    no total; INACTIVE inclui amostras inativas, não registros excluídos.

    Attributes:
        search: Texto opcional de pesquisa.
        status: Situação científica desejada, quando informada.
    """

    search: str | None = None
    status: AgentStatus | None = None


class BiologicalAgentStatusResponse(BaseSchema):
    """Confirma a alteração de estado do cadastro pelo N2 autorizado.

    Attributes:
        id: Identificador do agente alterado.
        status: Estado ACTIVE ou INACTIVE efetivamente gravado.
    """

    id: UUID
    status: AgentStatus
