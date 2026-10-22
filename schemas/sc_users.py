"""Schemas de users para contas, recuperação e identificação do usuário atual."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    Field, 
    EmailStr, 
    SecretStr, 
    model_validator,
    StringConstraints, 
)

from schemas.sc_roles import RoleCode
from schemas.sc_teams import TeamResponse
from schemas.sc_base_model import (
    Reason,
    BaseSchema, 
    AuditSchema, 
    NormalizedEmail,
    PaginationParams,
)

UserStatus = Literal["PENDING_ACTIVATION", "ACTIVE"]
UserName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

NewPassword = Annotated[SecretStr, Field(min_length=8, max_length=30)]


class UserSummary(BaseSchema):
    """Identifica uma pessoa em cards e seletores de responsável ou colaborador.

    Evita expor email, credenciais ou o diretório completo nas telas técnicas.
    O serviço continua responsável por filtrar pessoas elegíveis no mesmo grupo.

    Attributes:
        id: Identificador do usuário autorizado para essa consulta.
        name: Nome apresentado no card ou seletor.
    """

    id: UUID
    name: str


class UserResponse(AuditSchema):
    """Apresenta uma conta em GET /users e nas ações administrativas.

    Inclui os campos de AuditSchema e a data da primeira ativação, mas não
    hashes, vetores, tokens ou contadores biométricos internos. Desativação é
    representada por soft_delete, independentemente da situação da ativação.

    Attributes:
        id, name, email: Identificação da conta.
        role_code, team_id: Papel e equipe selecionados pelo backend.
        status: Etapa de ativação, sem o antigo estado DISABLED.
        activated_at: Primeira ativação, preservada em reativações.
        biometric_enrollment_required: Necessidade de cadastrar o rosto.
        password_change_required: Necessidade de definir uma nova senha.
    """

    id: UUID
    name: str
    email: EmailStr
    role_code: RoleCode
    team_id: UUID | None = None
    status: UserStatus
    activated_at: datetime | None = None
    biometric_enrollment_required: bool
    password_change_required: bool


class UserActivationResponse(UserResponse):
    """Apresenta conta e validade nas ações administrativas de ativação.

    Usada em reativação, renovação da temporária e recuperação. Herda os dados
    sanitizados e flags da conta; o serviço consulta a validade na credencial
    atual, sem retornar a senha, seu hash ou o token de uma tentativa.

    Attributes:
        temporary_expires_at: Validade da senha temporária quando aplicável;
            None quando a recuperação não envolve uma senha provisória.
    """

    temporary_expires_at: datetime | None = None


class UserUpdate(BaseSchema):
    """Recebe alterações institucionais em PATCH /users/{id}.

    Campos omitidos permanecem intactos; use model_dump(exclude_unset=True).
    Null explícito é rejeitado em todos os campos. Cargo, equipe, vagas e
    revogação são verificados no serviço.

    Attributes:
        name: Nome não vazio, normalizado nas extremidades.
        email: Email válido, convertido para minúsculas.
        role_code: Novo papel institucional.
        team_id: Identificador da equipe escolhida; omitir preserva o vínculo.
    """

    name: UserName | None = None
    email: NormalizedEmail | None = None
    role_code: RoleCode | None = None
    team_id: UUID | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        """Rejeita alterações vazias e null em campos obrigatórios da conta."""
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para alterar.")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"O campo {field} não aceita null.")
        return self


class UserDeactivate(BaseSchema):
    """Recebe o motivo de POST /users/{id}/deactivate.

    O backend determina autoria e momento, marca soft_delete e revoga as
    credenciais em transação. O cliente não escolhe campos de auditoria.

    Attributes:
        reason: Justificativa não vazia, limitada a 1.500 caracteres.
    """

    reason: Reason


class UserReactivate(BaseSchema):
    """Recebe os dados de POST /users/{id}/reactivate.

    A senha preserva seus espaços e fica mascarada na representação do modelo.
    O serviço verifica vaga e papel, restaura a conta, exige novas etapas e
    preserva activated_at. A senha nunca deve ser retornada nem registrada em log.

    Attributes:
        temporary_password: Nova senha temporária de 8 a 30 caracteres.
        reason: Justificativa não vazia, até 1.500 caracteres.
    """

    temporary_password: NewPassword
    reason: Reason


class UserRecovery(BaseSchema):
    """Recebe a recuperação administrada em POST /users/{id}/recovery.

    PASSWORD e BOTH exigem uma senha temporária; BIOMETRIC não aceita esse
    campo. Autorização, lista de senhas fracas, hashes, exclusão lógica dos
    vetores anteriores e revogação de credenciais pertencem ao serviço.

    Attributes:
        mode: Recuperação de senha, biometria ou ambas.
        reason: Justificativa administrativa, até 1.500 caracteres.
        temporary_password: Senha de 8 a 30 caracteres, quando exigida pelo modo.
    """

    mode: Literal["PASSWORD", "BIOMETRIC", "BOTH"]
    reason: Reason
    temporary_password: NewPassword | None = None

    @model_validator(mode="after")
    def validate_recovery_password(self) -> Self:
        """Exige ou rejeita a senha conforme o modo de recuperação solicitado."""
        if self.mode == "BIOMETRIC":
            if "temporary_password" in self.model_fields_set:
                raise ValueError("Recuperação biométrica não recebe senha temporária.")
        elif self.temporary_password is None:
            raise ValueError("Informe a senha temporária para recuperar a senha.")
        return self


class UserQuery(PaginationParams):
    """Define filtros administrativos de GET /users.

    Herda page e per_page. Consultar desativados exige autorização de ADMIN;
    os filtros não dão acesso ao conteúdo técnico nem alteram a conta.

    Attributes:
        search: Busca opcional por identificação da pessoa.
        status: Filtro pela situação da ativação.
        soft_delete: False para contas vigentes; True para consultar desativadas.
    """

    search: str | None = None
    status: UserStatus | None = None
    soft_delete: bool = False


class SessionUserResponse(UserSummary):
    """Acrescenta email, papel e equipe à identificação da sessão concluída.

    Usada em user nas respostas de login, biometria ou ativação concluídos.
    Herda id e name sem acrescentar credenciais, contadores ou dados do cofre.

    Attributes:
        email: Endereço da conta autenticada.
        role: Código do papel vigente.
        team: Equipe da pessoa, quando aplicável.
    """

    email: EmailStr
    role: RoleCode
    team: TeamResponse | None = None


class CurrentUserResponse(SessionUserResponse):
    """Apresenta a projeção sanitizada de GET /auth/me.

    Herda a identificação da sessão e adiciona permissões para orientar a
    interface. Cada operação continua exigindo autorização no backend, sem
    aceitar a lista enviada pelo navegador como prova de acesso.

    Attributes:
        permissions: Códigos de ações vigentes selecionados pelo backend.
    """

    permissions: list[str]


class UserCandidateQuery(PaginationParams):
    """Recebe pesquisa dos seletores de responsável e colaborador.

    Herda page e per_page e não permite escolher papel ou consultar desativados.
    O backend fixa N1 ativo, não excluído e do grupo autorizado da investigação.

    Attributes:
        search: Nome ou identificação a pesquisar no conjunto de candidatos.
    """

    search: str | None = None
