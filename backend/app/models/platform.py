"""Modelos del schema `platform` (PRD §4)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import Rol
from app.models.base import PlatformBase

_ROLES_SQL = ", ".join(f"'{rol.value}'" for rol in Rol)


def _ahora() -> Any:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Tenant(PlatformBase):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("plan IN ('free', 'pro', 'enterprise')", name="plan_valido"),
        CheckConstraint("schema_name ~ '^tenant_[0-9a-f]{32}$'", name="schema_name_valido"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    razon_social: Mapped[str] = mapped_column(String(200))
    nit: Mapped[str | None] = mapped_column(String(20), unique=True)
    nrc: Mapped[str | None] = mapped_column(String(20))
    plan: Mapped[str] = mapped_column(String(20), default="pro", server_default="pro")
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    schema_name: Mapped[str] = mapped_column(String(63), unique=True)
    created_at: Mapped[datetime] = _ahora()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    usuarios: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(PlatformBase):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"rol IN ({_ROLES_SQL})", name="rol_valido"),
        # Solo el SUPERADMIN vive fuera de una empresa, y nunca dentro de una.
        CheckConstraint("(rol = 'SUPERADMIN') = (tenant_id IS NULL)", name="superadmin_sin_tenant"),
        CheckConstraint("email = lower(email)", name="email_minusculas"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("platform.tenants.id", ondelete="RESTRICT"), index=True
    )
    email: Mapped[str] = mapped_column(String(200), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    nombre: Mapped[str | None] = mapped_column(String(100))
    apellido: Mapped[str | None] = mapped_column(String(100))
    rol: Mapped[str] = mapped_column(String(30))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Secreto TOTP cifrado con Fernet; el 2FA solo cuenta cuando totp_habilitado es verdadero.
    totp_secret: Mapped[str | None] = mapped_column(Text)
    totp_habilitado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    totp_ultimo_contador: Mapped[int | None] = mapped_column(BigInteger)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ahora()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    tenant: Mapped[Tenant | None] = relationship(back_populates="usuarios")


class UserSession(PlatformBase):
    """Sesión de refresh token. Se guarda solo el hash SHA-256 del token."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform.users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ahora()
    ultimo_uso_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_revocacion: Mapped[str | None] = mapped_column(String(50))


class PasswordResetToken(PlatformBase):
    """Token de un solo uso para recuperar contraseña (se guarda solo su hash)."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform.users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = _ahora()


class AuditLog(PlatformBase):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_tenant_id_created_at", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    accion: Mapped[str] = mapped_column(String(100))
    modulo: Mapped[str] = mapped_column(String(50))
    entidad_id: Mapped[str | None] = mapped_column(String(100))
    detalle: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ahora()
