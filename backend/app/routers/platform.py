"""/platform — gestión de empresas por el SUPERADMIN (FLUJOS §3)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.core.deps import Contexto, DbDep, requiere_permiso
from app.core.permissions import Accion, Modulo
from app.models.platform import AuditLog, Tenant
from app.schemas.platform import TenantActualizar, TenantCreado, TenantCrear, TenantSalida
from app.schemas.usuarios import AuditoriaSalida, UsuarioSalida
from app.services import tenant_service

router = APIRouter(prefix="/platform", tags=["Plataforma"])

LeerTenants = Annotated[Contexto, Depends(requiere_permiso(Modulo.GESTION_TENANTS, Accion.LEER))]
EscribirTenants = Annotated[Contexto, Depends(requiere_permiso(Modulo.GESTION_TENANTS, Accion.ESCRIBIR))]


@router.get("/tenants", response_model=list[TenantSalida], summary="Listar empresas")
def listar_tenants(
    ctx: LeerTenants,
    db: DbDep,
    activo: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Tenant]:
    consulta = select(Tenant).order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
    if activo is not None:
        consulta = consulta.where(Tenant.activo.is_(activo))
    return list(db.scalars(consulta))


@router.post(
    "/tenants",
    response_model=TenantCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Crear empresa (schema, migraciones y usuario ADMIN)",
)
def crear_tenant(datos: TenantCrear, ctx: EscribirTenants, db: DbDep) -> TenantCreado:
    """El administrador inicial recibe una contraseña temporal y debe cambiarla al entrar."""
    tenant, admin = tenant_service.crear_tenant(db, datos, ctx.user, ctx.cliente)
    return TenantCreado(tenant=TenantSalida.model_validate(tenant), admin=UsuarioSalida.model_validate(admin))


@router.get("/tenants/{tenant_id}", response_model=TenantSalida, summary="Ver empresa")
def ver_tenant(tenant_id: uuid.UUID, ctx: LeerTenants, db: DbDep) -> Tenant:
    return tenant_service.obtener_tenant(db, tenant_id)


@router.patch("/tenants/{tenant_id}", response_model=TenantSalida, summary="Editar datos de empresa")
def actualizar_tenant(
    tenant_id: uuid.UUID, datos: TenantActualizar, ctx: EscribirTenants, db: DbDep
) -> Tenant:
    tenant = tenant_service.obtener_tenant(db, tenant_id)
    return tenant_service.actualizar_tenant(db, tenant, datos, ctx.user, ctx.cliente)


@router.post("/tenants/{tenant_id}/suspender", response_model=TenantSalida, summary="Suspender empresa")
def suspender_tenant(tenant_id: uuid.UUID, ctx: EscribirTenants, db: DbDep) -> Tenant:
    tenant = tenant_service.obtener_tenant(db, tenant_id)
    return tenant_service.cambiar_estado(db, tenant, False, ctx.user, ctx.cliente)


@router.post("/tenants/{tenant_id}/activar", response_model=TenantSalida, summary="Reactivar empresa")
def activar_tenant(tenant_id: uuid.UUID, ctx: EscribirTenants, db: DbDep) -> Tenant:
    tenant = tenant_service.obtener_tenant(db, tenant_id)
    return tenant_service.cambiar_estado(db, tenant, True, ctx.user, ctx.cliente)


@router.get("/auditoria", response_model=list[AuditoriaSalida], summary="Auditoría de toda la plataforma")
def auditoria_plataforma(
    ctx: Annotated[Contexto, Depends(requiere_permiso(Modulo.GESTION_TENANTS, Accion.LEER))],
    db: DbDep,
    tenant_id: uuid.UUID | None = None,
    accion: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLog]:
    consulta = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    if tenant_id is not None:
        consulta = consulta.where(AuditLog.tenant_id == tenant_id)
    if accion:
        consulta = consulta.where(AuditLog.accion == accion)
    return list(db.scalars(consulta))
