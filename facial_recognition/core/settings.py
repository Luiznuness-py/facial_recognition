"""Configuração obrigatória e seleção de ambiente e modo biométrico."""
import re
from typing import Literal
from datetime import datetime
from urllib.parse import quote

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Carrega a configuração da aplicação a partir do ambiente e do arquivo .env.

    As variáveis do processo têm prioridade sobre o arquivo. Campos extras são ignorados e
    os nomes são sensíveis a maiúsculas. O mesmo DB_NAME é usado em todos os ambientes; o
    pool seleciona o schema.

    Attributes:
        APP_NAME, APP_VERSION: Identificação pública da aplicação.
        DATE_TIME: Instante textual local calculado ao criar a configuração.
        DEBUG, ASYNC_MODE: Opções legadas declaradas na configuração.
        ENVIRONMENT: Ambiente normalizado em minúsculas.
        BIOMETRICS_MODE: Modo obrigatório real/simulated; simulação só em development/test.
        ADMIN_EMAIL, ADMIN_SECRET: Credenciais usadas pelo seed ao criar o primeiro ADMIN.
        DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME: Parâmetros de conexão PostgreSQL.
        DATABASE_ECHO: Opção declarada para configuração de consultas.
        SECRET_KEY: Raiz criptográfica usada na derivação de chaves.
        ALGORITHM: Opção legada; TokenJwt fixa HS256 no código.
        ACCESS_TOKEN_EXPIRE, REFRESH_TOKEN_EXPIRE: Opções legadas que não controlam os
            prazos fixos do fluxo atual.
    """
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )
    # PATTERN CONFIGURATIONS
    APP_NAME: str = Field(default="Facial Recognition", env="APP_NAME")
    APP_VERSION: str = Field(default="0.0.1", description="Application version")
    DATE_TIME: str = Field(
        default_factory=lambda: datetime.now().strftime(
            "%Y-%m-%d'T'%H:%M:%S.%f")[:-3]
    )
    DEBUG: bool = Field(default=True, env="DEBUG_MODE")
    ENVIRONMENT: str = Field(
        default="development", description="Environment (development, production, test)")
    BIOMETRICS_MODE: Literal["real", "simulated"] = Field(
        ..., description="Modo obrigatório da biometria: real ou simulated")
    ASYNC_MODE: bool = Field( default=True, description="liga/desliga async engine")
    
    # Security Configurations
    ADMIN_EMAIL: str = Field(default="admin@facialrecognition.com", env="ADMIN_EMAIL")
    ADMIN_SECRET: str = Field(env="ADMIN_SECRET")
    
    # Database Configuration - Using separate parameters (NOT DATABASE_URL)
    DB_USER: str = Field(default="postgres", description="Database user")
    DB_PASSWORD: str = Field(default="postgrespwd", description="Database password")
    DB_HOST: str = Field(default="localhost", description="Database host")
    DB_PORT: int = Field(default=5432, description="Database port")
    DB_NAME: str = Field(default="appdb", description="Database name")
    DATABASE_ECHO: bool = Field(default=False, description="Echo SQL queries")

    # JWT
    SECRET_KEY: str = Field(..., description='Chave secreta para criar e validar um JWT')
    ALGORITHM: str = Field(default='HS256', description='Algorithm de criptografia do JWT')
    ACCESS_TOKEN_EXPIRE: int = Field(default=30, description='Tem de expiração do ACCESS TOKEN em minutos')
    REFRESH_TOKEN_EXPIRE: int = Field(default=30, description='Tem de expiração do REFRESH TOKEN em dias')

    _SQL_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"--"),
        re.compile(r"/\*"),
        re.compile(r"\*/"),
        re.compile(r"(?i)\bunion\b\s+\bselect\b"),
        re.compile(r"(?i)\bdrop\b\s+\btable\b"),
        re.compile(r"(?i)\bor\b\s+1\s*=\s*1\b"),
    )

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def environment_lowercase(cls, v: str) -> str:
        """Normaliza o nome do ambiente antes da validação do campo.

        Args:
            v: Nome textual recebido da variável de ambiente ou do arquivo.

        Returns:
            str: Nome convertido para minúsculas; não restringe o conjunto de ambientes.
        """
        return v.lower()
    
    @model_validator(mode="after")
    def validate_biometrics_mode(self):
        """Impede simulação fora dos ambientes locais explicitamente permitidos."""
        if self.BIOMETRICS_MODE == "simulated" and self.ENVIRONMENT not in {"development", "test"}:
            raise ValueError("Biometria simulada permitida somente em development ou test.")
        return self

    def get_database_url(self) -> str:
        """Monta a DSN PostgreSQL usando sempre o banco DB_NAME.

        Não abre conexões nem escolhe schema. Não deve ser registrada em logs porque contém
        a senha do banco.

        Returns:
            str: URL com usuário, senha e nome de banco escapados para uso pelo asyncpg.
        """
        return (
            f"postgresql://{quote(self.DB_USER, safe='')}:"
            f"{quote(self.DB_PASSWORD, safe='')}@"
            f"{self.DB_HOST}:{self.DB_PORT}/"
            f"{quote(self.DB_NAME, safe='')}"
        )


# Global settings instance
settings = Settings()
