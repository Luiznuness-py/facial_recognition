"""Emissão e validação dos JWTs; sessão e permissões são conferidas no banco."""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from jwt import InvalidTokenError, decode, encode

from facial_recognition.core.settings import settings


class TokenJwt:
    """Emite e valida JWTs com configuração compartilhada entre as requisições.

    Mantém apenas a raiz secreta. Usuário, sessão e tentativa não são guardados nesta
    instância; o estado vigente é consultado no banco pelas dependências das rotas.

    Attributes:
        secret: Raiz secreta em bytes usada na derivação das chaves por propósito.
    """

    def __init__(self, secret: str = settings.SECRET_KEY):
        """Valida e armazena a raiz secreta usada pelos tokens.

        O tamanho mínimo é verificado; a geração aleatória e o armazenamento seguro do
        segredo são responsabilidades da configuração.

        Args:
            secret: Segredo do servidor, obtido de SECRET_KEY quando omitido.

        Raises:
            ValueError: Quando a representação UTF-8 tem menos de 32 bytes.
        """
        if len(secret.encode()) < 32:
            raise ValueError('SECRET_KEY precisa ter pelo menos 32 bytes aleatórios.')
        self.secret = secret.encode()

    def key(self, purpose: str) -> bytes:
        """Deriva uma chave independente para um propósito específico.

        Args:
            purpose: Identificador interno, como ACCESS, RESTRICTED, CSRF ou VECTORS.

        Returns:
            bytes: Chave HMAC-SHA256 derivada da raiz e do identificador versionado.
        """
        mode_suffix = ':simulated' if settings.BIOMETRICS_MODE == 'simulated' else ''
        return hmac.digest(self.secret, f'aps-lab:{purpose}:v1{mode_suffix}'.encode(), 'sha256')

    def create_token(self, user_id, token_type: str, lifetime: int, **claims) -> str:
        """Assina um JWT com identidade, finalidade e expiração controladas pelo servidor.

        Claims reservados são definidos pelo método. Um jti fornecido é preservado para
        vincular o token à tentativa; os demais casos recebem um UUID novo. A emissão não
        grava o token no banco.

        Args:
            user_id: Identificador da conta que será convertido para o claim sub.
            token_type: Finalidade do token, usada também para selecionar a chave.
            lifetime: Validade em segundos a partir do instante UTC atual.
            claims: Claims adicionais; access recebe session_id e restrito recebe
                attempt_id, stage e operation.

        Returns:
            str: JWT assinado com HS256, iss e aud fixos.
        """
        now = datetime.now(timezone.utc)
        payload = dict(claims, sub=str(user_id), type=token_type, jti=str(claims.get('jti', uuid4())),
                       iat=now, exp=now + timedelta(seconds=lifetime), iss='aps-lab', aud='aps-lab-api')
        return encode(payload, self.key(token_type), algorithm='HS256')

    def validate_token(self, token: str | None, expected_type: str) -> dict:
        """Valida a assinatura, o prazo e os claims obrigatórios da finalidade esperada.

        Confere issuer, audience e UUIDs. Não verifica revogação, soft_delete, permissões ou
        o estado da sessão/tentativa.

        Args:
            token: JWT recebido no cookie; None representa credencial ausente.
            expected_type: ACCESS para sessão ou RESTRICTED para uma etapa.

        Returns:
            dict: Claims autenticados, ainda sujeitos à conferência de estado no banco.

        Raises:
            HTTPException: Status 401 para ausência, expiração, assinatura, finalidade ou
                identificadores inválidos.
        """
        required = ['sub', 'type', 'jti', 'iat', 'exp', 'iss', 'aud']
        required += ['session_id'] if expected_type == 'ACCESS' else ['attempt_id', 'stage', 'operation']
        try:
            if not token:
                raise ValueError('missing')
            payload = decode(token, self.key(expected_type), algorithms=['HS256'],
                             issuer='aps-lab', audience='aps-lab-api', options={'require': required})
            if payload['type'] != expected_type:
                raise ValueError('type')
            for field in ['sub', 'jti', 'session_id' if expected_type == 'ACCESS' else 'attempt_id']:
                UUID(payload[field])
            return payload
        except (InvalidTokenError, ValueError, TypeError, AttributeError):
            raise HTTPException(401, 'Credencial ausente, inválida ou expirada.') from None
