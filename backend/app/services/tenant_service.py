"""Alta y administración de empresas (FLUJOS §3: crear schema, migrar, crear ADMIN)."""

import uuid

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import InfoCliente, registrar
from app.core.errors import ErrorServicio
from app.core.permissions import Rol
from app.core.security import ahora, hash_password
from app.core.tenant import tenant_schema
from app.migraciones import migrar_tenant
from app.models.platform import Tenant, User, UserSession
from app.schemas.platform import TenantActualizar, TenantCrear
from app.services.auth_service import normalizar_email

MODULO = "platform"


def _verificar_unicos(db: Session, *, slug: str | None, nit: str | None, excluir: uuid.UUID | None) -> None:
    condiciones = []
    if slug:
        condiciones.append(Tenant.slug == slug)
    if nit:
        condiciones.append(Tenant.nit == nit)
    if not condiciones:
        return
    consulta = select(Tenant).where(or_(*condiciones))
    if excluir is not None:
        consulta = consulta.where(Tenant.id != excluir)
    existente = db.scalar(consulta.limit(1))
    if existente is not None:
        campo = "slug" if slug and existente.slug == slug else "NIT"
        raise ErrorServicio(409, f"Ya existe una empresa con ese {campo}")


def crear_tenant(db: Session, datos: TenantCrear, actor: User, cliente: InfoCliente) -> tuple[Tenant, User]:
    """Todo ocurre en una sola transacción: si algo falla no queda schema ni registros a medias."""
    _verificar_unicos(db, slug=datos.slug, nit=datos.nit, excluir=None)
    email_admin = normalizar_email(datos.admin.email)
    if db.scalar(select(User.id).where(User.email == email_admin)) is not None:
        raise ErrorServicio(409, "Ya existe un usuario con ese correo")

    tenant_id = uuid.uuid4()
    tenant = Tenant(
        id=tenant_id,
        slug=datos.slug,
        razon_social=datos.razon_social,
        nit=datos.nit,
        nrc=datos.nrc,
        plan=datos.plan,
        activo=True,
        schema_name=tenant_schema(tenant_id),
    )
    db.add(tenant)
    db.flush()
    migrar_tenant(db.connection(), tenant.schema_name)

    admin = User(
        tenant_id=tenant.id,
        email=email_admin,
        hashed_password=hash_password(datos.admin.password_temporal),
        nombre=datos.admin.nombre,
        apellido=datos.admin.apellido,
        rol=Rol.ADMIN_EMPRESA.value,
        debe_cambiar_password=True,
    )
    db.add(admin)
    db.flush()
    registrar(
        db,
        accion="platform.tenant_creado",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=tenant.id,
        user_id=actor.id,
        entidad_id=tenant.id,
        detalle={"slug": tenant.slug, "plan": tenant.plan, "admin_id": str(admin.id)},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ErrorServicio(409, "Ya existe una empresa o un usuario con esos datos") from None
    return tenant, admin


def obtener_tenant(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ErrorServicio(404, "Empresa no encontrada")
    return tenant


def actualizar_tenant(
    db: Session, tenant: Tenant, datos: TenantActualizar, actor: User, cliente: InfoCliente
) -> Tenant:
    cambios = datos.model_dump(exclude_unset=True)
    if "razon_social" in cambios and cambios["razon_social"] is None:
        raise ErrorServicio(422, "La razón social no puede quedar vacía")
    if "plan" in cambios and cambios["plan"] is None:
        raise ErrorServicio(422, "El plan no puede quedar vacío")
    _verificar_unicos(db, slug=None, nit=cambios.get("nit"), excluir=tenant.id)
    for campo, valor in cambios.items():
        setattr(tenant, campo, valor)
    registrar(
        db,
        accion="platform.tenant_actualizado",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=tenant.id,
        user_id=actor.id,
        entidad_id=tenant.id,
        detalle={"campos": sorted(cambios)},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ErrorServicio(409, "Ya existe una empresa con ese NIT") from None
    return tenant


def cambiar_estado(db: Session, tenant: Tenant, activo: bool, actor: User, cliente: InfoCliente) -> Tenant:
    """Suspender bloquea el acceso de inmediato y cierra todas las sesiones de la empresa.

    No borra datos (DECISIONES: deshabilitar oculta y deniega, sin eliminar).
    """
    if tenant.activo == activo:
        return tenant
    tenant.activo = activo
    if not activo:
        usuarios = select(User.id).where(User.tenant_id == tenant.id)
        db.execute(
            update(UserSession)
            .where(UserSession.user_id.in_(usuarios), UserSession.revocada_at.is_(None))
            .values(revocada_at=ahora(), motivo_revocacion="empresa_suspendida"),
            execution_options={"synchronize_session": False},
        )
    registrar(
        db,
        accion="platform.tenant_activado" if activo else "platform.tenant_suspendido",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=tenant.id,
        user_id=actor.id,
        entidad_id=tenant.id,
    )
    db.commit()
    return tenant
