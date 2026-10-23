"""Configuración mediante variables de entorno; nunca incrustar credenciales."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = Field(default="development", pattern="^(development|test|production)$")
    database_url: SecretStr
    secret_key: SecretStr

    # Tokens (PRD §3.2: access 15 min + refresh 7 días)
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # Bloqueo por intentos fallidos (PRD §3.2: bloqueo tras 5 intentos)
    max_intentos_login: int = Field(default=5, ge=3, le=20)
    bloqueo_minutos: int = Field(default=30, ge=1)
    password_reset_expire_minutes: int = Field(default=60, ge=5, le=1440)
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)

    # Cifrado en reposo con Fernet (secretos TOTP, luego certificados y API keys DTE)
    fernet_key: SecretStr | None = None

    # Frontend y CORS
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = ""

    # Correo saliente
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True

    # SuperAdmin inicial (solo se usa si todavía no existe ninguno)
    superadmin_email: str | None = None
    superadmin_password: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _validar_produccion(self) -> "Settings":
        if self.environment == "production" and len(self.secret_key.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY debe tener al menos 32 caracteres en producción")
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        """URL con el driver explícito `psycopg2`.

        Render y otros proveedores entregan `postgres://` o `postgresql://` sin driver, y
        SQLAlchemy 2.1 asume `psycopg` (v3) en ese caso, que no está instalado.
        """
        url = self.database_url.get_secret_value()
        for prefijo in ("postgres://", "postgresql://"):
            if url.startswith(prefijo):
                return "postgresql+psycopg2://" + url.removeprefix(prefijo)
        return url

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
