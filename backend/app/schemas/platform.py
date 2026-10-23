import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, EmailStr, StringConstraints

from app.schemas.comun import EsquemaSalida, Nit, Nrc, PasswordNueva, TextoCorto
from app.schemas.usuarios import UsuarioSalida

Plan = Literal["free", "pro", "enterprise"]
Slug = Annotated[
    str,
    BeforeValidator(lambda valor: valor.strip().lower() if isinstance(valor, str) else valor),
    StringConstraints(min_length=3, max_length=50, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"),
]
RazonSocial = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class AdminInicial(BaseModel):
    email: EmailStr
    nombre: TextoCorto
    apellido: TextoCorto
    password_temporal: PasswordNueva


class TenantCrear(BaseModel):
    slug: Slug
    razon_social: RazonSocial
    nit: Nit = None
    nrc: Nrc = None
    plan: Plan = "pro"
    admin: AdminInicial


class TenantActualizar(BaseModel):
    razon_social: RazonSocial | None = None
    nit: Nit = None
    nrc: Nrc = None
    plan: Plan | None = None


class TenantSalida(EsquemaSalida):
    id: uuid.UUID
    slug: str
    razon_social: str
    nit: str | None
    nrc: str | None
    plan: str
    activo: bool
    schema_name: str
    created_at: datetime


class TenantCreado(BaseModel):
    tenant: TenantSalida
    admin: UsuarioSalida
