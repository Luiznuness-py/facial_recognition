"""Schemas do login e das respostas de sessão; credenciais ficam em cookies HttpOnly."""

from typing import Literal

from pydantic import Field, SecretStr

from facial_recognition.schemas.users import SessionUserResponse
from facial_recognition.schemas.base_model import BaseSchema, NormalizedEmail
from facial_recognition.schemas.authentication_attempts import AuthenticationStepResponse


class LoginRequest(BaseSchema):
    """Recebe email e senha em POST /auth/login.

    Normaliza somente o email. Preserva a senha, mascarando-a na representação
    do modelo. O backend verifica a conta, exclusão lógica e credenciais antes
    de escolher a próxima etapa; este schema não autentica o usuário.

    Attributes:
        email: Endereço válido normalizado para busca da conta.
        password: Senha não vazia, com até 30 caracteres e sem strip.
    """

    email: NormalizedEmail
    password: SecretStr = Field(min_length=1, max_length=30)


class SessionResponse(BaseSchema):
    """Descreve a sessão concluída, sem expor tokens no JSON.

    Usada quando login, biometria ou ativação concluem as etapas exigidas. O
    backend emite cookies e calcula a validade restante, sem prolongar as 24h.

    Attributes:
        next_step: SESSION, indicando que a sessão normal foi concedida.
        expires_in: Segundos restantes de validade, entre 1 e 86.400.
        user: Identificação sanitizada, papel e equipe da pessoa.
    """

    next_step: Literal["SESSION"] = "SESSION"
    expires_in: int = Field(gt=0, le=86400)
    user: SessionUserResponse


class LoginRequiredResponse(BaseSchema):
    """Informa que a pessoa deve entrar novamente após trocar a senha.

    Usada em /auth/password-change/complete após revogar credenciais e limpar
    cookies. A resposta não contém sessão, token ou senha.

    Attributes:
        next_step: LOGIN, orientando a interface a voltar à entrada.
    """

    next_step: Literal["LOGIN"] = "LOGIN"


class CsrfResponse(BaseSchema):
    """Entrega o token de proteção de GET /auth/csrf.

    O token é destinado ao JavaScript e não autentica a pessoa. O backend gera
    e verifica a assinatura ligada ao contexto e emite o cookie apropriado.

    Attributes:
        csrf_token: Token de proteção enviado em X-CSRF-Token nas mutações.
    """

    csrf_token: str = Field(min_length=1)


LoginResponse = AuthenticationStepResponse | SessionResponse
