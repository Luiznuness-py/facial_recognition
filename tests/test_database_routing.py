"""Roteamento por ambiente não depende de opt-in manual em cada chamada."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from facial_recognition.core.database import drop_all_tables
from facial_recognition.core.settings import settings


@pytest.mark.parametrize('environment', ['development', 'test', 'production'])
def test_database_is_the_same_in_every_environment(monkeypatch, environment):
    """Confere o uso de DB_NAME sem troca de banco entre os ambientes.

    Args:
        monkeypatch: Fixture pytest que restaura atributos e substituições ao terminar o
            caso.
        environment: Nome do ambiente parametrizado no caso de teste.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    monkeypatch.setattr(settings, 'DB_NAME', 'shared_database')
    monkeypatch.setattr(settings, 'ENVIRONMENT', environment)
    assert settings.get_database_url().endswith('/shared_database')


@pytest.mark.parametrize('environment,schema', [('test', 'test'), ('development', 'public')])
def test_reset_targets_environment_schema(monkeypatch, environment, schema):
    """Confere, com conexão simulada, que o reset usa somente o schema do ambiente.

    Args:
        monkeypatch: Fixture pytest que restaura atributos e substituições ao terminar o
            caso.
        environment: Nome do ambiente parametrizado no caso de teste.
        schema: Schema esperado para o reset simulado.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    monkeypatch.setattr(settings, 'ENVIRONMENT', environment)
    connection = MagicMock()
    connection.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = connection

    asyncio.run(drop_all_tables(pool))

    assert connection.execute.await_args_list == [
        call(f'DROP SCHEMA {schema} CASCADE'),
        call(f'CREATE SCHEMA {schema}'),
    ]
    connection.transaction.return_value.__aexit__.assert_awaited_once()


def test_reset_rejects_production_without_acquiring_connection(monkeypatch):
    """Confere que o reset é recusado em produção antes de adquirir conexão.

    Args:
        monkeypatch: Fixture pytest que restaura atributos e substituições ao terminar o
            caso.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'production')
    pool = MagicMock()

    with pytest.raises(RuntimeError):
        asyncio.run(drop_all_tables(pool))

    pool.acquire.assert_not_called()
