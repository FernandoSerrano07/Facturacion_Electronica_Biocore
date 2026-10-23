import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from app.core.permissions import Rol
from app.schemas.comun import EsquemaSalida, PasswordNueva, TextoCorto


def _rol_de_empresa(rol: Rol) -> Rol:
    if rol is Rol.SUPERADMIN:
        raise ValueError("SUPERADMIN no se puede asignar a usuarios de una empresa")
    return rol


class UsuarioCrear(BaseModel):
    email: EmailStr
    nombre: TextoCorto
    apellido: TextoCorto
    rol: Rol
    password_temporal: PasswordNueva

    @field_validator("rol")
    @classmethod
    def _validar_rol(cls, rol: Rol) -> Rol:
        return _rol_de_empresa(rol)


class UsuarioActualizar(BaseModel):
    nombre: TextoCorto | None = None
    apellido: TextoCorto | None = None
    rol: Rol | None = None
    activo: bool | None = None

    @field_validator("rol")
    @classmethod
    def _validar_rol(cls, rol: Rol | None) -> Rol | None:
        return _rol_de_empresa(rol) if rol is not None else None


class PasswordTemporalEntrada(BaseModel):
    password_temporal: PasswordNueva


class UsuarioSalida(EsquemaSalida):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    email: str
    nombre: str | None
    apellido: str | None
    rol: str
    activo: bool
    totp_habilitado: bool
    debe_cambiar_password: bool
    bloqueado_hasta: datetime | None
    ultimo_login: datetime | None
    created_at: datetime


class AuditoriaSalida(EsquemaSalida):
    id: int
    tenant_id: uuid.UUID | None
    user_id: uuid.UUID | None
    accion: str
    modulo: str
    entidad_id: str | None
    detalle: dict | None
    ip: str | None
    user_agent: str | None
    created_at: datetime
