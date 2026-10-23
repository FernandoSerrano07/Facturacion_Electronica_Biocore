"""Dependencias FastAPI: usuario autenticado, permisos RBAC y sesión con schema de empresa.

El token solo identifica la sesión. Rol, estado del usuario y estado de la empresa
se leen siempre de la base de datos, así una suspensión o un cambio de rol se aplica
en la siguiente petición sin esperar a que expire el access token.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.audit import InfoCliente, info_cliente
from app.core.permissions import Accion, Modulo, Rol, tiene_permiso
from app.core.security import TIPO_ACCESS, TokenInvalido, ahora, decodificar_token
from app.core.tenant import set_tenant_schema
from app.database import get_db
from app.models.platform import Tenant, User, UserSession

_bearer = HTTPBearer(auto_error=False, description="Access token JWT obtenido en /auth/login")


@dataclass
class Contexto:
    user: User
    sesion: UserSession
    tenant: Tenant | None
    cliente: InfoCliente

    @property
    def rol(self) -> Rol:
        return Rol(self.user.rol)

    @property
    def tenant_id(self) -> uuid.UUID | None:
        return self.tenant.id if self.tenant else None


def _no_autenticado(detalle: str = "No autenticado") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


DbDep = Annotated[Session, Depends(get_db)]


def get_contexto_base(
    request: Request,
    db: DbDep,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Contexto:
    """Valida el token y la sesión. Permite usuarios que deben cambiar su contraseña."""
    if credenciales is None or credenciales.scheme.lower() != "bearer":
        raise _no_autenticado()
    try:
        payload = decodificar_token(credenciales.credentials, TIPO_ACCESS)
    except TokenInvalido:
        raise _no_autenticado("Token inválido o expirado") from None

    sesion = db.get(UserSession, payload["sid"])
    if (
        sesion is None
        or sesion.user_id != payload["sub"]
        or sesion.revocada_at is not None
        or sesion.expires_at <= ahora()
    ):
        raise _no_autenticado("La sesión ya no es válida")

    user = db.get(User, payload["sub"])
    if user is None or not user.activo or user.deleted_at is not None:
        raise _no_autenticado("Usuario inactivo")

    tenant = None
    if user.tenant_id is not None:
        tenant = db.get(Tenant, user.tenant_id)
        if tenant is None or not tenant.activo:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "La empresa está inactiva")

    return Contexto(user=user, sesion=sesion, tenant=tenant, cliente=info_cliente(request))


ContextoBaseDep = Annotated[Contexto, Depends(get_contexto_base)]


def get_contexto(ctx: ContextoBaseDep) -> Contexto:
    """Usuario autenticado y con contraseña definitiva."""
    if ctx.user.debe_cambiar_password:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Debes cambiar tu contraseña antes de continuar (POST /auth/password/cambiar)",
        )
    return ctx


ContextoDep = Annotated[Contexto, Depends(get_contexto)]


def requiere_permiso(modulo: Modulo, accion: Accion = Accion.LEER) -> Callable[..., Contexto]:
    """Dependencia que exige el permiso de la matriz RBAC para el módulo."""

    def _verificar(ctx: ContextoDep) -> Contexto:
        if not tiene_permiso(ctx.rol, modulo, accion):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta acción")
        return ctx

    _verificar.__name__ = f"requiere_{modulo.value}_{accion.value}"
    return _verificar


def requiere_empresa(modulo: Modulo, accion: Accion = Accion.LEER) -> Callable[..., Contexto]:
    """Como `requiere_permiso`, pero además exige que el usuario pertenezca a una empresa."""
    verificar_permiso = requiere_permiso(modulo, accion)

    def _verificar(ctx: Annotated[Contexto, Depends(verificar_permiso)]) -> Contexto:
        if ctx.tenant is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Este recurso pertenece al panel de una empresa")
        return ctx

    _verificar.__name__ = f"requiere_empresa_{modulo.value}_{accion.value}"
    return _verificar


def get_tenant_db(ctx: ContextoDep, db: DbDep) -> Session:
    """Sesión con el search_path fijado al schema de la empresa del usuario autenticado."""
    if ctx.tenant is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Este recurso pertenece al panel de una empresa")
    set_tenant_schema(db, ctx.tenant.id)
    return db


TenantDbDep = Annotated[Session, Depends(get_tenant_db)]
