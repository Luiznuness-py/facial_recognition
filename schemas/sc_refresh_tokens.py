"""Resposta da renovação; refresh_tokens e seus hashes permanecem internos."""

from pydantic import Field

from schemas.sc_base_model import BaseSchema


class RefreshTokenResponse(BaseSchema):
    """Apresenta somente a validade devolvida por POST /auth/refresh.

    O refresh é recebido por cookie HttpOnly e seu sucessor é emitido em outro
    cookie. Rotação, uso único, revogação e prazo absoluto são conferidos no
    serviço; o schema não recebe nem devolve o token ou seu hash.

    Attributes:
        expires_in: Segundos de validade do novo access token, até 15 minutos,
            limitados também pelo tempo restante da sessão.
    """

    expires_in: int = Field(gt=0, le=900)
