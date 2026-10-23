"""Configuración mediante variables de entorno; nunca incrustar credenciales."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = Field(default="development", pattern="^(development|test|production)$")
    database_url: SecretStr
    secret_key: SecretStr

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
