"""Senhas, criptografia de vetores, cookies e proteção de requisições browser."""

import hashlib
import hmac
import secrets
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, Request, Response

from facial_recognition.core.token_jwt import TokenJwt
from facial_recognition.core.settings import settings

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Gera o hash Argon2id de uma senha para armazenamento.

    Não valida a política da senha nem grava no banco. A validação de novas senhas deve
    ocorrer antes desta chamada.

    Args:
        password: Senha original, com espaços e maiúsculas preservados.

    Returns:
        str: Hash codificado com algoritmo, parâmetros e salt aleatório.
    """
    return password_hasher.hash(password)


def check_password(password: str, encoded: str) -> bool:
    """Confere uma senha com o hash atual sem modificar a credencial.

    Args:
        password: Senha recebida, sem normalização.
        encoded: Hash Argon2 codificado armazenado no banco.

    Returns:
        bool: True se a senha corresponde; False para senha incorreta ou hash inválido.
    """
    try:
        return password_hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


@cache
def common_passwords() -> frozenset[str]:
    """Carrega e mantém em cache a lista local de senhas previsíveis.

    O arquivo é lido no primeiro uso e não é consultado pela rede. Sua ausência impede a
    criação de novas senhas, sem interferir na verificação de hashes existentes.

    Returns:
        frozenset[str]: Senhas em casefold para comparação sem distinção de caixa.

    Raises:
        OSError: Quando passwords.txt não pode ser lido.
    """
    return frozenset((Path(__file__).resolve().parents[1] / 'utils' / 'passwords.txt').read_text().casefold().splitlines())


def validate_new_password(password: str) -> None:
    """Aplica a política de tamanho e de senhas previsíveis.

    Args:
        password: Senha candidata, cujo conteúdo não é aparado.

    Returns:
        None: A ausência de exceção indica aprovação nesta política.

    Raises:
        HTTPException: Status 422 para tamanho fora de 8 a 128 caracteres ou senha presente
            na lista local.
        OSError: Quando a lista de senhas não pode ser carregada.
    """
    if not 8 <= len(password) <= 128:
        raise HTTPException(422, 'A senha deve ter entre 8 e 128 caracteres.')
    if password.casefold() in common_passwords():
        raise HTTPException(422, 'A senha é muito fraca. Escolha outra senha.')


def token_hash(token: str) -> str:
    """Calcula a impressão SHA-256 de um token opaco.

    Não substitui Argon2 para senhas. O uso pressupõe tokens aleatórios gerados pelo
    servidor.

    Args:
        token: Valor original do token; não deve ser registrado em logs.

    Returns:
        str: Digest hexadecimal separado por modo para localizar refresh tokens no banco.
    """
    # Credenciais opacas de simulação não podem renovar sessões no modo real.
    value = 'simulated:' + token if settings.BIOMETRICS_MODE == 'simulated' else token
    return hashlib.sha256(value.encode()).hexdigest()


def set_cookie(response: Response, request: Request, name: str, value: str, lifetime: int) -> None:
    """Define um cookie HttpOnly com escopo de caminho e transporte controlados.

    Usa SameSite=strict e Secure em HTTPS. Access e contexto CSRF ficam no caminho /api/v1.

    Args:
        response: Resposta que receberá o cabeçalho Set-Cookie.
        request: Requisição usada para conferir host e protocolo.
        name: Nome do cookie; stage e refresh ficam em /api/v1/auth.
        value: Conteúdo do cookie que será enviado ao navegador.
        lifetime: Prazo em segundos, ajustado para no mínimo um segundo.

    Returns:
        None: A resposta é modificada no próprio objeto.

    Raises:
        HTTPException: Status 400 quando HTTP não é local em development ou test.
    """
    secure = request.url.scheme == 'https'
    local = request.url.hostname in {'127.0.0.1', 'localhost', '::1'}
    allow_http = settings.ENVIRONMENT in {'development', 'test'} and local
    if not secure and not allow_http:
        raise HTTPException(400, 'Use HTTPS para acessar a aplicação.')
    path = '/api/v1/auth' if name in {'lab_stage', 'lab_refresh'} else '/api/v1'
    response.set_cookie(name, value, max_age=max(1, lifetime), path=path,
                        httponly=True, secure=secure, samesite='strict')


def clear_cookies(response: Response) -> None:
    """Expira os cookies de autenticação e de contexto CSRF.

    Repete os caminhos originais para remover os cookies corretos. A revogação de sessões e
    tentativas no banco é responsabilidade de quem chama esta função.

    Args:
        response: Resposta que enviará as instruções de remoção dos cookies.

    Returns:
        None: Os cabeçalhos são acrescentados à resposta.
    """
    for name in ['lab_access', 'lab_refresh', 'lab_stage', 'lab_csrf_context']:
        path = '/api/v1/auth' if name in {'lab_stage', 'lab_refresh'} else '/api/v1'
        response.delete_cookie(name, path=path, httponly=True, samesite='strict')


def rotate_csrf(response: Response, request: Request) -> str:
    """Substitui o contexto aleatório que participa da proteção CSRF.

    Args:
        response: Resposta que receberá o novo cookie de contexto.
        request: Requisição usada para aplicar as regras de transporte.

    Returns:
        str: Novo contexto aleatório, usado para assinar o token de proteção.

    Raises:
        HTTPException: Status 400 se o cookie não puder ser emitido pelo transporte
            utilizado.
    """
    context = secrets.token_urlsafe(32)
    set_cookie(response, request, 'lab_csrf_context', context, 86400)
    return context


def csrf_signature(request: Request, context: str) -> str:
    """Assina a associação entre o contexto CSRF e o cookie de acesso atual.

    Prefere o cookie de etapa, depois access e, na ausência de ambos, usa o contexto
    anônimo. Não valida esses cookies nem concede autenticação.

    Args:
        request: Requisição com a configuração criptográfica e os cookies recebidos.
        context: Contexto aleatório armazenado no cookie HttpOnly.

    Returns:
        str: HMAC hexadecimal usado no cabeçalho X-CSRF-Token.
    """
    binding = request.cookies.get('lab_stage') or request.cookies.get('lab_access') or 'anonymous'
    return hmac.new(request.app.state.tokens.key('CSRF'),
                    f'{context}:{token_hash(binding)}'.encode(), hashlib.sha256).hexdigest()


def verify_origin(request: Request) -> None:
    """Exige que a origem informada corresponda à origem desta aplicação.

    Args:
        request: Requisição com Origin ou Referer e os cabeçalhos de navegação.

    Returns:
        None: A ausência de exceção autoriza a origem para as verificações seguintes.

    Raises:
        HTTPException: Status 403 para origem ausente, diferente ou
            Sec-Fetch-Site=cross-site.
    """
    source = request.headers.get('origin') or request.headers.get('referer')
    expected = urlsplit(str(request.base_url))
    actual = urlsplit(source or '')
    if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc) or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Origem da requisição não permitida.')


async def require_csrf(request: Request) -> None:
    """Valida a origem e a assinatura CSRF de uma requisição de alteração.

    Compara a assinatura em tempo constante. Esta dependência protege a requisição, mas não
    identifica o usuário nem substitui a autorização da rota.

    Args:
        request: Requisição que deve conter contexto CSRF e X-CSRF-Token.

    Returns:
        None: Permite que o FastAPI continue a execução das dependências e da rota.

    Raises:
        HTTPException: Status 403 se a origem, o contexto ou a assinatura forem inválidos.
    """
    verify_origin(request)
    context = request.cookies.get('lab_csrf_context', '')
    received = request.headers.get('x-csrf-token', '')
    if not context or not hmac.compare_digest(received, csrf_signature(request, context)):
        raise HTTPException(403, 'Proteção da requisição expirada. Tente novamente.')


def encrypt_vector(tokens: TokenJwt, user_id, data: bytes) -> tuple[bytes, bytes]:
    """Criptografa os bytes de um template facial com AES-GCM.

    Vincular o UUID como dado associado impede reutilizar o mesmo conteúdo protegido como
    cadastro de outra conta.

    Args:
        tokens: Configuração usada para derivar a chave de propósito VECTORS.
        user_id: UUID da conta, utilizado como dado associado da criptografia.
        data: Bytes serializados do template, sem alteração de formato.

    Returns:
        tuple[bytes, bytes]: Conteúdo criptografado com tag de autenticação e nonce
            aleatório de 12 bytes.
    """
    nonce = secrets.token_bytes(12)
    return AESGCM(tokens.key('VECTORS')).encrypt(nonce, data, str(user_id).encode()), nonce


def decrypt_vector(tokens: TokenJwt, user_id, ciphertext: bytes, nonce: bytes) -> bytes:
    """Autentica e descriptografa um template facial vinculado à conta.

    Args:
        tokens: Configuração com a mesma raiz usada na criptografia.
        user_id: UUID que deve corresponder ao dado associado original.
        ciphertext: Conteúdo protegido, incluindo a tag de autenticação.
        nonce: Valor de 12 bytes armazenado com o conteúdo.

    Returns:
        bytes: Template serializado no formato que foi originalmente criptografado.

    Raises:
        InvalidTag: Quando a chave, o usuário ou o conteúdo não correspondem aos dados
            originais.
        ValueError: Quando o nonce possui tamanho inválido.
    """
    return AESGCM(tokens.key('VECTORS')).decrypt(nonce, ciphertext, str(user_id).encode())
