"""Cadastro inicial do ADMIN, preservando contas e senhas já existentes."""
import asyncio
from datetime import datetime, timedelta, timezone

from facial_recognition.core.security import hash_password, validate_new_password


async def seed_admin(connection, email: str, password: str):
    """Cadastra o ADMIN inicial somente quando ainda não existe um administrador.

    A existência de ADMIN inclui contas excluídas logicamente: o seed não restaura nem
    duplica o administrador. Não redefine senha ao alterar o .env. O chamador deve fornecer
    a transação e o lock do bootstrap.

    Args:
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.
        email: Email configurado para a nova conta, normalizado nas extremidades e em
            minúsculas.
        password: Senha temporária usada apenas se uma conta precisar ser criada.

    Returns:
        None: Mantém o ADMIN existente ou insere a conta e seu hash temporário.

    Raises:
        RuntimeError: Quando o email pertence a outro papel ou ADMIN está ausente/desativado
            no catálogo.
        HTTPException: Status 422 quando a nova senha não atende à política.
    """
    existing = await connection.fetchval("SELECT EXISTS(SELECT 1 FROM users u JOIN roles r ON r.id=u.role_id WHERE r.code='ADMIN')")
    if existing:
        return
    email = email.strip().lower()
    if await connection.fetchval('SELECT EXISTS(SELECT 1 FROM users WHERE email=$1)', email):
        raise RuntimeError('ADMIN_EMAIL pertence a uma conta que não é ADMIN; revise a configuração.')
    validate_new_password(password)
    encoded = await asyncio.to_thread(hash_password, password)
    role = await connection.fetchval("SELECT id FROM roles WHERE code='ADMIN' AND NOT soft_delete")
    if role is None:
        raise RuntimeError('Papel ADMIN está desativado ou ausente; revise o catálogo.')
    user = await connection.fetchval("""INSERT INTO users(name,email,role_id,biometric_enrollment_required)
        VALUES('Administrador',$1,$2,FALSE) RETURNING id""", email, role)
    await connection.execute('INSERT INTO password_hashes(user_id,password_hash,is_temporary,temporary_expires_at) VALUES($1,$2,TRUE,$3)',
                             user, encoded, datetime.now(timezone.utc)+timedelta(hours=24))
