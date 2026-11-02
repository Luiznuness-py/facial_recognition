"""Consulta SQL base da conta, papel e credencial vigente."""
class UserQueries:

    """Agrupa consultas SQL relacionadas às contas dos usuários."""
    USER_SQL = """
        SELECT u.*, r.code AS role, p.password_hash, p.is_temporary, p.temporary_expires_at,
        p.soft_delete AS password_deleted FROM users u JOIN roles r ON r.id=u.role_id AND NOT r.soft_delete
        JOIN password_hashes p ON p.user_id=u.id WHERE NOT u.soft_delete
    """
