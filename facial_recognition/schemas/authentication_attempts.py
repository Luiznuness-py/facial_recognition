"""Projeções de authentication_attempts para as etapas restritas de autenticação."""

from typing import Literal

from pydantic import Field

from facial_recognition.schemas.base_model import BaseSchema

AuthStage = Literal["ENROLL_FACE", "VERIFY_FACE", "CHANGE_PASSWORD"]
AuthOperation = Literal["LOGIN", "ACTIVATION", "RECOVERY", "PASSWORD_CHANGE"]


class AuthenticationStepResponse(BaseSchema):
    """Informa a próxima etapa sem conceder acesso normal ao laboratório.

    Usada por login, biometria, início de troca e recuperação quando ainda
    existem etapas pendentes. JWT, identificador da tentativa e contadores
    internos não são incluídos; o backend emite o cookie restrito.

    Attributes:
        next_step: Cadastro facial, reconhecimento facial ou troca de senha.
        expires_in: Segundos restantes da etapa, limitados aos cinco minutos.
    """

    next_step: AuthStage
    expires_in: int = Field(gt=0, le=300)


class AuthenticationFlowResponse(AuthenticationStepResponse):
    """Permite retomar a tela correta por GET /auth/flow.

    Acrescenta a operação à próxima etapa e validade herdadas. O backend verifica
    o cookie e a tentativa e não renova o prazo ao consultar este recurso.

    Attributes:
        operation: Fluxo de entrada, ativação, recuperação ou troca de senha.
        biometrics_mode: Modo informado pelo servidor para escolher a tela facial.
    """

    operation: AuthOperation
    biometrics_mode: Literal["real", "simulated"]
