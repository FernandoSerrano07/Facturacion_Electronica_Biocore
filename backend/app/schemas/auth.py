import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.comun import EsquemaSalida, PasswordNueva

CodigoTotp = Field(pattern=r"^\d{6}$", description="Código de 6 dígitos de la app autenticadora")


class LoginEntrada(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class Login2FAEntrada(BaseModel):
    token_2fa: str = Field(min_length=1, max_length=2000)
    codigo: str = CodigoTotp


class UsuarioActual(EsquemaSalida):
    id: uuid.UUID
    email: str
    nombre: str | None
    apellido: str | None
    rol: str
    tenant_id: uuid.UUID | None
    totp_habilitado: bool
    debe_cambiar_password: bool


class EmpresaActual(EsquemaSalida):
    id: uuid.UUID
    slug: str
    razon_social: str
    plan: str


class Perfil(BaseModel):
    usuario: UsuarioActual
    empresa: EmpresaActual | None
    ruta_inicial: str
    permisos: dict[str, str]


class SesionIniciada(BaseModel):
    requiere_2fa: Literal[False] = False
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Segundos de vigencia del access token")
    ruta_inicial: str
    usuario: UsuarioActual


class DesafioDosFactores(BaseModel):
    requiere_2fa: Literal[True] = True
    token_2fa: str
    expires_in: int


class TokenRenovado(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class SesionInfo(EsquemaSalida):
    id: uuid.UUID
    ip: str | None
    user_agent: str | None
    created_at: datetime
    ultimo_uso_at: datetime | None
    expires_at: datetime
    actual: bool = False


class Configuracion2FA(BaseModel):
    secreto: str
    otpauth_uri: str = Field(description="Mostrar como código QR en la app autenticadora")


class CodigoEntrada(BaseModel):
    codigo: str = CodigoTotp


class Desactivar2FAEntrada(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    codigo: str = CodigoTotp


class OlvidePasswordEntrada(BaseModel):
    email: EmailStr


class RestablecerPasswordEntrada(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    nueva_password: PasswordNueva


class CambiarPasswordEntrada(BaseModel):
    password_actual: str = Field(min_length=1, max_length=200)
    nueva_password: PasswordNueva
