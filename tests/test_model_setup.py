"""Verifica a inicialização sem pesos, sem acessar rede ou PostgreSQL."""
import asyncio
from unittest.mock import AsyncMock

import pytest

import facial_recognition.app as application


def test_startup_rejects_missing_models_before_opening_database(monkeypatch):
    """Recusa iniciar a API e orienta a restauração dos arquivos quando os pesos não carregam.

    Args:
        monkeypatch: Substitui o carregamento e o pool, impedindo rede ou acesso ao banco.
    """
    def missing_models(self):
        """Simula a ausência de pesos locais.

        Args:
            self: Instância FaceModels preparada pelo lifespan.

        Raises:
            FileNotFoundError: Representa um peso ausente no disco.
        """
        raise FileNotFoundError('model.pth')

    pool = AsyncMock()
    monkeypatch.setattr(application.FaceModels, 'load', missing_models)
    monkeypatch.setattr(application, 'create_pool', pool)

    async def start():
        """Executa o contexto de inicialização que deve falhar antes de liberar a API.

        Raises:
            RuntimeError: Propaga a orientação de preparação emitida pelo lifespan.
        """
        async with application.lifespan(application.app):
            pytest.fail('A API iniciou sem os pesos')

    with pytest.raises(RuntimeError, match='Restaure os quatro arquivos'):
        asyncio.run(start())
    pool.assert_not_awaited()
