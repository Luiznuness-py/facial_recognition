from datetime import datetime
from urllib.parse import quote

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    IMPORTANT: This configuration uses separate database connection parameters
    instead of a single DATABASE_URL string. This provides better flexibility
    and security when managing database connections.
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
    DEBUG: bool = Field(default=False, env="DEBUG_MODE")
    ENVIRONMENT: str = Field(
        default="development", description="Environment (development, production, test)")
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
    DB_NAME_TEST: str = Field(default="appdb_test", description="Test database name")
    DATABASE_ECHO: bool = Field(default=False, description="Echo SQL queries")

    # JWT
    SECRET_KEY: str = Field(..., description='Chave secreta para criar e validar um JWT')
    ALGORITHM: str = Field(default='HS256', description='Algorithm de criptografia do JWT')
    ACCESS_TOKEN_EXPIRE: int = Field(default=30, description='Tem de expiração do ACCESS TOKEN em minutos')
    REFRESH_TOKEN_EXPIRE: int = Field(default=30, description='Tem de expiração do REFRESH TOKEN em dias')

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def environment_lowercase(cls, v: str) -> str:
        """Normaliza o nome do ambiente para letras minúsculas."""
        return v.lower()
    
    def get_database_url(self, use_test_db: bool = False) -> str:
        """Monta a DSN PostgreSQL usada pelo asyncpg para o banco escolhido."""
        database = self.DB_NAME_TEST if use_test_db else self.DB_NAME

        return (
            f"postgresql://{quote(self.DB_USER, safe='')}:"
            f"{quote(self.DB_PASSWORD, safe='')}@"
            f"{self.DB_HOST}:{self.DB_PORT}/"
            f"{quote(database, safe='')}"
        )


# Global settings instance
settings = Settings()
