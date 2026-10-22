"""Entradas das ações de senha; password_hashes não tem CRUD público ou resposta de hash."""

from typing import Self

from pydantic import Field, SecretStr, model_validator

from facial_recognition.schemas.users import NewPassword
from facial_recognition.schemas.base_model import BaseSchema


class PasswordCompleteRequest(BaseSchema):
    """Recebe a nova senha em ativação ou conclusão de troca voluntária.

    Atende /auth/password/complete e /auth/password-change/complete. Preserva
    espaços, valida 8 a 30 caracteres e confere a confirmação. O serviço valida
    credenciais de etapa, senhas previsíveis, hash e revogação das sessões.

    Attributes:
        new_password: Senha definitiva, mascarada na representação do modelo.
        password_confirmation: Repetição exata da nova senha.
    """

    new_password: NewPassword
    password_confirmation: NewPassword

    @model_validator(mode="after")
    def validate_confirmation(self) -> Self:
        """Rejeita senhas diferentes sem normalizar nem expor os valores."""
        if self.new_password.get_secret_value() != self.password_confirmation.get_secret_value():
            raise ValueError("A confirmação da senha não corresponde à nova senha.")
        return self


class PasswordChangeStartRequest(BaseSchema):
    """Recebe a prova de senha atual em /auth/password-change/start.

    O serviço verifica a senha e a sessão autenticada antes de autorizar face
    ou troca. A senha recebida não pode ser retornada nem registrada em log.

    Attributes:
        current_password: Senha atual não vazia, preservada sem strip.
    """

    current_password: SecretStr = Field(min_length=1, max_length=30)
