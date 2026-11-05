"""Autorização de ações por permissões vigentes no PostgreSQL."""
from fastapi import Depends, HTTPException

from facial_recognition.core.database import Connection
from facial_recognition.core.authentication import Authentication


authentication = Authentication()


class Authorization:
    """Valida uma permissão do papel da conta autenticada.

    Attributes:
        code: Código da permissão exigida pela rota.
    """

    def __init__(self, code: str):
        """Define qual permissão será consultada.

        Args:
            code: Código da permissão institucional exigida pela rota.
        """
        self.code = code

    async def __call__(
        self,
        connection: Connection,
        user=Depends(authentication.get_current_user),
    ):
        """Autoriza a conta quando seu papel possui a permissão exigida.

        Args:
            connection: Conexão PostgreSQL da requisição.
            user: Conta autenticada por get_current_user.

        Returns:
            asyncpg.Record: Conta autenticada e autorizada.

        Raises:
            HTTPException: Status 403 quando a conta não possui a permissão.
        """
        query = """
            SELECT EXISTS (
                SELECT 1
                FROM role_permissions AS rp
                JOIN permissions AS p
                    ON p.id = rp.permission_id
                WHERE rp.role_id = $1
                    AND p.code = $2
                    AND NOT rp.soft_delete
                    AND NOT p.soft_delete
            )
        """

        allowed = await connection.fetchval(
            query,
            user["role_id"],
            self.code,
        )

        # Permissão configurada não remove a exclusividade institucional do cofre N3.
        n3_only = self.code in {'vault.read', 'vault.decide', 'publications.read', 'publications.publish'}
        if not allowed or (n3_only and user['role'] != 'N3'):
            raise HTTPException(
                status_code=403,
                detail="Sua conta não possui permissão para esta ação.",
            )

        return user
