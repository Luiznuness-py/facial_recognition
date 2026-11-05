"""Regras compartilhadas de contas, vagas institucionais e revogação."""
import asyncio
from datetime import timedelta

from fastapi import HTTPException

from facial_recognition.core.security import hash_password, validate_new_password
from facial_recognition.utils.utils import now


async def password_hash(password):
    """Valida a senha antes de calcular Argon2 fora do loop HTTP.

    Extrai a SecretStr, aplica a política local e calcula Argon2 em thread, sem gravar
    credenciais.

    Args:
        password: SecretStr com a nova senha, preservando espaços e maiúsculas.

    Returns:
        str: Hash Argon2id pronto para persistência.

    Raises:
        HTTPException: Status 422 quando a nova senha viola a política.
        OSError: Quando a lista local de senhas não pode ser lida.
    """
    value = password.get_secret_value()
    validate_new_password(value)
    return await asyncio.to_thread(hash_password, value)


async def check_position(connection, role_code, team_id, user_id=None):
    """Valida papel, equipe e vaga sob o lock transacional do cadastro.

    Usa o advisory lock transacional de cadastros. Contas não excluídas, inclusive pendentes de
    ativação, ocupam a posição N2/N3.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        role_code: Código institucional ADMIN, N1, N2 ou N3 a validar no catálogo.
        team_id: UUID da equipe para N1/N2, ou None para papéis sem equipe.
        user_id: UUID da própria conta a excluir da contagem, ou None em um novo cadastro.

    Returns:
        UUID: Identificador do papel vigente que atende às regras.

    Raises:
        HTTPException: Status 422 para papel/equipe incompatíveis; 409 para posição ocupada.
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    await connection.execute('SELECT pg_advisory_xact_lock(827462)')
    role = await connection.fetchval('SELECT id FROM roles WHERE code=$1 AND NOT soft_delete', role_code)
    if role is None or (role_code in {'N1', 'N2'}) != (team_id is not None):
        raise HTTPException(422, 'Papel e equipe incompatíveis.')
    if team_id and not await connection.fetchval('SELECT EXISTS(SELECT 1 FROM teams WHERE id=$1 AND NOT soft_delete)', team_id):
        raise HTTPException(422, 'Equipe inválida.')
    if role_code in {'N2', 'N3'} and await connection.fetchval('''SELECT EXISTS(SELECT 1 FROM users
        WHERE role_id=$1 AND NOT soft_delete AND ($2::uuid IS NULL OR team_id=$2)
        AND ($3::uuid IS NULL OR id<>$3))''', role, team_id, user_id):
        raise HTTPException(409, 'A posição deste papel já está ocupada.')
    return role


async def revoke_access(connection, user_id):
    """Revoga sessões antes dos refresh e tentativas; o chamador mantém o lock da conta.

    Exige transação e lock da conta pelo chamador. Atualiza sessões antes de refresh e cancela
    tentativas pendentes, preservando o histórico.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user_id: UUID da conta cujos acessos ou credenciais serão atualizados.

    Returns:
        None: Revoga o acesso sem confirmar a transação do chamador.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    await connection.execute('UPDATE sessions SET revoked_at=NOW() WHERE user_id=$1 AND revoked_at IS NULL', user_id)
    await connection.execute('''UPDATE refresh_tokens SET revoked_at=NOW() WHERE session_id IN
        (SELECT id FROM sessions WHERE user_id=$1) AND revoked_at IS NULL''', user_id)
    await connection.execute("UPDATE authentication_attempts SET status='CANCELLED' WHERE user_id=$1 AND status='PENDING'", user_id)


async def set_temporary_password(connection, user_id, encoded, actor):
    """Substitui a credencial por uma temporária válida por 24 horas.

    Insere ou substitui a credencial por uma temporária de 24 horas. Restaura a linha da senha e
    registra o autor; não confirma a transação.

    Args:
        connection: Conexão asyncpg do schema atual; a transação pertence ao chamador quando
            indicada.
        user_id: UUID da conta cujos acessos ou credenciais serão atualizados.
        encoded: Hash Argon2 já validado e calculado; nunca a senha em texto.
        actor: UUID da conta que executa a operação e será registrada na autoria.

    Returns:
        datetime: Expiração UTC da temporária persistida.

    Raises:
        asyncpg.PostgresError: Quando a consulta ou gravação no schema atual falha.
    """
    expires = now() + timedelta(hours=24)
    await connection.execute('''INSERT INTO password_hashes(user_id,password_hash,is_temporary,temporary_expires_at,created_by)
        VALUES($1,$2,TRUE,$3,$4) ON CONFLICT(user_id) DO UPDATE SET password_hash=$2,is_temporary=TRUE,
        temporary_expires_at=$3,soft_delete=FALSE,updated_at=NOW(),updated_by=$4''', user_id, encoded, expires, actor)
    return expires
