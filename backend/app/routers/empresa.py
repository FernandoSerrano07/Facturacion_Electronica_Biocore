"""/empresa — usuarios y auditoría de la empresa del usuario autenticado (FLUJOS §4).

Todas las consultas filtran por el `tenant_id` del usuario autenticado (tomado de la
base de datos, no del token): un usuario de otra empresa responde 404, igual que uno inexistente.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.core.audit import registrar
from app.core.deps import Contexto, DbDep, requiere_empresa
from app.core.errors import ErrorServicio
from app.core.permissions import Accion, Modulo
from app.core.security import hash_password
from app.models.platform import AuditLog, User
from app.schemas.usuarios import (
    AuditoriaSalida,
    PasswordTemporalEntrada,
    UsuarioActualizar,
    UsuarioCrear,
    UsuarioSalida,
)
from app.services.auth_service import normalizar_email, revocar_sesiones

router = APIRouter(prefix="/empresa", tags=["Empresa"])

MODULO = "usuarios"
LeerUsuarios = Annotated[Contexto, Depends(requiere_empresa(Modulo.USUARIOS, Accion.LEER))]
EscribirUsuarios = Annotated[Contexto, Depends(requiere_empresa(Modulo.USUARIOS, Accion.ESCRIBIR))]
LeerAuditoria = Annotated[Contexto, Depends(requiere_empresa(Modulo.AUDITORIA, Accion.LEER))]


def _usuario_de_empresa(db: DbDep, ctx: Contexto, user_id: uuid.UUID) -> User:
    user = db.scalar(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id, User.deleted_at.is_(None))
    )
    if user is None:
        raise ErrorServicio(404, "Usuario no encontrado")
    return user


@router.get("/usuarios", response_model=list[UsuarioSalida], summary="Usuarios de mi empresa")
def listar_usuarios(
    ctx: LeerUsuarios,
    db: DbDep,
    activo: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    consulta = (
        select(User)
        .where(User.tenant_id == ctx.tenant_id, User.deleted_at.is_(None))
        .order_by(User.created_at)
        .limit(limit)
        .offset(offset)
    )
    if activo is not None:
        consulta = consulta.where(User.activo.is_(activo))
    return list(db.scalars(consulta))


@router.post(
    "/usuarios",
    response_model=UsuarioSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario con contraseña temporal",
)
def crear_usuario(datos: UsuarioCrear, ctx: EscribirUsuarios, db: DbDep) -> User:
    email = normalizar_email(datos.email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ErrorServicio(409, "Ya existe un usuario con ese correo")
    user = User(
        tenant_id=ctx.tenant_id,
        email=email,
        hashed_password=hash_password(datos.password_temporal),
        nombre=datos.nombre,
        apellido=datos.apellido,
        rol=datos.rol.value,
        debe_cambiar_password=True,
    )
    db.add(user)
    db.flush()
    registrar(
        db,
        accion="usuarios.creado",
        modulo=MODULO,
        cliente=ctx.cliente,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        entidad_id=user.id,
        detalle={"rol": user.rol},
    )
    db.commit()
    return user


@router.get("/usuarios/{user_id}", response_model=UsuarioSalida, summary="Ver usuario")
def ver_usuario(user_id: uuid.UUID, ctx: LeerUsuarios, db: DbDep) -> User:
    return _usuario_de_empresa(db, ctx, user_id)


@router.patch(
    "/usuarios/{user_id}", response_model=UsuarioSalida, summary="Editar, cambiar rol o activar/desactivar"
)
def actualizar_usuario(
    user_id: uuid.UUID, datos: UsuarioActualizar, ctx: EscribirUsuarios, db: DbDep
) -> User:
    user = _usuario_de_empresa(db, ctx, user_id)
    cambios = datos.model_dump(exclude_unset=True)
    for campo in ("rol", "activo", "nombre", "apellido"):
        if campo in cambios and cambios[campo] is None:
            raise ErrorServicio(422, f"El campo {campo} no puede quedar vacío")
    if user.id == ctx.user.id and ({"rol", "activo"} & cambios.keys()):
        raise ErrorServicio(403, "No puedes cambiar tu propio rol ni desactivarte")

    if "rol" in cambios:
        cambios["rol"] = cambios["rol"].value
    for campo, valor in cambios.items():
        setattr(user, campo, valor)
    if cambios.get("activo") is False:
        revocar_sesiones(db, user.id, "usuario_desactivado")

    registrar(
        db,
        accion="usuarios.actualizado",
        modulo=MODULO,
        cliente=ctx.cliente,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        entidad_id=user.id,
        detalle={campo: cambios[campo] for campo in ("rol", "activo") if campo in cambios}
        | {"campos": sorted(cambios)},
    )
    db.commit()
    return user


@router.post("/usuarios/{user_id}/desbloquear", response_model=UsuarioSalida, summary="Desbloquear cuenta")
def desbloquear_usuario(user_id: uuid.UUID, ctx: EscribirUsuarios, db: DbDep) -> User:
    user = _usuario_de_empresa(db, ctx, user_id)
    user.bloqueado_hasta = None
    user.intentos_fallidos = 0
    registrar(
        db,
        accion="usuarios.desbloqueado",
        modulo=MODULO,
        cliente=ctx.cliente,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        entidad_id=user.id,
    )
    db.commit()
    return user


@router.post(
    "/usuarios/{user_id}/restablecer-password",
    response_model=UsuarioSalida,
    summary="Asignar contraseña temporal (cierra sus sesiones)",
)
def asignar_password_temporal(
    user_id: uuid.UUID, datos: PasswordTemporalEntrada, ctx: EscribirUsuarios, db: DbDep
) -> User:
    user = _usuario_de_empresa(db, ctx, user_id)
    if user.id == ctx.user.id:
        raise ErrorServicio(403, "Para tu propia cuenta usa /auth/password/cambiar")
    user.hashed_password = hash_password(datos.password_temporal)
    user.debe_cambiar_password = True
    user.bloqueado_hasta = None
    user.intentos_fallidos = 0
    revocar_sesiones(db, user.id, "password_temporal")
    registrar(
        db,
        accion="usuarios.password_temporal",
        modulo=MODULO,
        cliente=ctx.cliente,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        entidad_id=user.id,
    )
    db.commit()
    return user


@router.post(
    "/usuarios/{user_id}/desactivar-2fa",
    response_model=UsuarioSalida,
    summary="Quitar 2FA (por ejemplo, si el usuario perdió su teléfono)",
)
def desactivar_2fa_usuario(user_id: uuid.UUID, ctx: EscribirUsuarios, db: DbDep) -> User:
    user = _usuario_de_empresa(db, ctx, user_id)
    user.totp_habilitado = False
    user.totp_secret = None
    user.totp_ultimo_contador = None
    revocar_sesiones(db, user.id, "2fa_reiniciado")
    registrar(
        db,
        accion="usuarios.2fa_desactivado",
        modulo=MODULO,
        cliente=ctx.cliente,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        entidad_id=user.id,
    )
    db.commit()
    return user


@router.get("/auditoria", response_model=list[AuditoriaSalida], summary="Log de acciones de mi empresa")
def auditoria_empresa(
    ctx: LeerAuditoria,
    db: DbDep,
    user_id: uuid.UUID | None = None,
    accion: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLog]:
    consulta = (
        select(AuditLog)
        .where(AuditLog.tenant_id == ctx.tenant_id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if user_id is not None:
        consulta = consulta.where(AuditLog.user_id == user_id)
    if accion:
        consulta = consulta.where(AuditLog.accion == accion)
    return list(db.scalars(consulta))
