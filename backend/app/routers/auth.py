"""/auth — login, 2FA, refresh, logout, sesiones activas y contraseñas (PRD §3.2)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.config import get_settings
from app.core.audit import info_cliente, registrar
from app.core.deps import ContextoBaseDep, ContextoDep, DbDep
from app.core.errors import ErrorServicio
from app.core.permissions import RUTA_INICIAL, Rol, permisos_de
from app.core.security import ahora
from app.models.platform import UserSession
from app.schemas.auth import (
    CambiarPasswordEntrada,
    CodigoEntrada,
    Configuracion2FA,
    Desactivar2FAEntrada,
    DesafioDosFactores,
    EmpresaActual,
    Login2FAEntrada,
    LoginEntrada,
    OlvidePasswordEntrada,
    Perfil,
    RestablecerPasswordEntrada,
    SesionInfo,
    SesionIniciada,
    TokenRenovado,
    UsuarioActual,
)
from app.schemas.comun import Mensaje
from app.services import auth_service, email_service

router = APIRouter(prefix="/auth", tags=["Autenticación"])

COOKIE_REFRESH = "biocore_refresh"
RUTA_COOKIE = "/auth"


def _fijar_cookie_refresh(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_REFRESH,
        token,
        max_age=settings.refresh_token_expire_days * 86400,
        path=RUTA_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def _borrar_cookie_refresh(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        COOKIE_REFRESH,
        path=RUTA_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def _respuesta_sesion(response: Response, emitida: auth_service.SesionEmitida) -> SesionIniciada:
    _fijar_cookie_refresh(response, emitida.refresh_token)
    return SesionIniciada(
        access_token=emitida.access_token,
        expires_in=emitida.expires_in,
        ruta_inicial=RUTA_INICIAL[Rol(emitida.user.rol)],
        usuario=UsuarioActual.model_validate(emitida.user),
    )


RefreshCookie = Annotated[str | None, Cookie(alias=COOKIE_REFRESH, include_in_schema=False)]


@router.post(
    "/login",
    response_model=SesionIniciada | DesafioDosFactores,
    summary="Iniciar sesión con correo y contraseña",
    responses={401: {"description": "Credenciales inválidas"}, 423: {"description": "Cuenta bloqueada"}},
)
def login(datos: LoginEntrada, request: Request, response: Response, db: DbDep):
    """Devuelve el access token (y deja el refresh token en una cookie HttpOnly).

    Si el usuario tiene 2FA activo, devuelve `requiere_2fa: true` y un `token_2fa`
    que se completa en `/auth/login/2fa`.
    """
    resultado = auth_service.iniciar_sesion(db, datos.email, datos.password, info_cliente(request))
    if isinstance(resultado, auth_service.Desafio2FA):
        return DesafioDosFactores(token_2fa=resultado.token, expires_in=resultado.expires_in)
    return _respuesta_sesion(response, resultado)


@router.post("/login/2fa", response_model=SesionIniciada, summary="Completar login con código TOTP")
def login_2fa(datos: Login2FAEntrada, request: Request, response: Response, db: DbDep):
    emitida = auth_service.completar_2fa(db, datos.token_2fa, datos.codigo, info_cliente(request))
    return _respuesta_sesion(response, emitida)


@router.post("/refresh", response_model=TokenRenovado, summary="Renovar el access token")
def refresh(request: Request, response: Response, db: DbDep, refresh_token: RefreshCookie = None):
    try:
        emitida = auth_service.renovar_sesion(db, refresh_token, info_cliente(request))
    except ErrorServicio as exc:
        if exc.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        rechazo = JSONResponse(status_code=exc.status_code, content={"detail": exc.detalle})
        _borrar_cookie_refresh(rechazo)
        return rechazo
    _fijar_cookie_refresh(response, emitida.refresh_token)
    return TokenRenovado(access_token=emitida.access_token, expires_in=emitida.expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar la sesión actual")
def logout(request: Request, db: DbDep, refresh_token: RefreshCookie = None) -> Response:
    auth_service.cerrar_sesion(db, refresh_token, info_cliente(request))
    respuesta = Response(status_code=status.HTTP_204_NO_CONTENT)
    _borrar_cookie_refresh(respuesta)
    return respuesta


@router.get("/me", response_model=Perfil, summary="Usuario autenticado, empresa y permisos")
def me(ctx: ContextoBaseDep) -> Perfil:
    return Perfil(
        usuario=UsuarioActual.model_validate(ctx.user),
        empresa=EmpresaActual.model_validate(ctx.tenant) if ctx.tenant else None,
        ruta_inicial=RUTA_INICIAL[ctx.rol],
        permisos=permisos_de(ctx.rol),
    )


# --- Sesiones activas -------------------------------------------------------------


@router.get("/sesiones", response_model=list[SesionInfo], summary="Mis sesiones activas")
def listar_sesiones(ctx: ContextoDep, db: DbDep) -> list[SesionInfo]:
    sesiones = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == ctx.user.id,
            UserSession.revocada_at.is_(None),
            UserSession.expires_at > ahora(),
        )
        .order_by(UserSession.created_at.desc())
    )
    salida = []
    for sesion in sesiones:
        info = SesionInfo.model_validate(sesion)
        info.actual = sesion.id == ctx.sesion.id
        salida.append(info)
    return salida


@router.delete(
    "/sesiones/{sesion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar una de mis sesiones (otro dispositivo)",
)
def cerrar_sesion_remota(sesion_id: uuid.UUID, ctx: ContextoDep, db: DbDep) -> None:
    sesion = db.get(UserSession, sesion_id)
    if sesion is None or sesion.user_id != ctx.user.id or sesion.revocada_at is not None:
        raise ErrorServicio(404, "Sesión no encontrada")
    sesion.revocada_at = ahora()
    sesion.motivo_revocacion = "cerrada_por_usuario"
    registrar(
        db,
        accion="auth.sesion_revocada",
        modulo="auth",
        cliente=ctx.cliente,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        entidad_id=sesion.id,
    )
    db.commit()


@router.post("/sesiones/cerrar-otras", response_model=Mensaje, summary="Cerrar todas mis otras sesiones")
def cerrar_otras_sesiones(ctx: ContextoDep, db: DbDep) -> Mensaje:
    cerradas = auth_service.revocar_sesiones(db, ctx.user.id, "cerrada_por_usuario", excepto=ctx.sesion.id)
    registrar(
        db,
        accion="auth.sesiones_revocadas",
        modulo="auth",
        cliente=ctx.cliente,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        detalle={"cantidad": cerradas},
    )
    db.commit()
    return Mensaje(mensaje=f"Se cerraron {cerradas} sesiones")


# --- 2FA --------------------------------------------------------------------------


@router.post("/2fa/configurar", response_model=Configuracion2FA, summary="Generar secreto TOTP (paso 1)")
def configurar_2fa(ctx: ContextoDep, db: DbDep) -> Configuracion2FA:
    config = auth_service.configurar_2fa(db, ctx.user)
    return Configuracion2FA(secreto=config.secreto, otpauth_uri=config.uri)


@router.post(
    "/2fa/activar", status_code=status.HTTP_204_NO_CONTENT, summary="Confirmar código y activar 2FA (paso 2)"
)
def activar_2fa(datos: CodigoEntrada, ctx: ContextoDep, db: DbDep) -> None:
    auth_service.activar_2fa(db, ctx.user, datos.codigo, ctx.cliente)


@router.post("/2fa/desactivar", status_code=status.HTTP_204_NO_CONTENT, summary="Desactivar 2FA")
def desactivar_2fa(datos: Desactivar2FAEntrada, ctx: ContextoDep, db: DbDep) -> None:
    auth_service.desactivar_2fa(db, ctx.user, datos.password, datos.codigo, ctx.cliente)


# --- Contraseñas --------------------------------------------------------------------


@router.post(
    "/password/olvide",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Mensaje,
    summary="Solicitar enlace de recuperación por correo",
)
def olvide_password(
    datos: OlvidePasswordEntrada, request: Request, background: BackgroundTasks, db: DbDep
) -> Mensaje:
    correo = auth_service.solicitar_recuperacion(db, datos.email, info_cliente(request))
    if correo is not None:
        background.add_task(email_service.enviar_correo, correo)
    return Mensaje(
        mensaje="Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."
    )


@router.post(
    "/password/restablecer",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Restablecer contraseña con el token del correo",
)
def restablecer_password(datos: RestablecerPasswordEntrada, request: Request, db: DbDep) -> None:
    auth_service.restablecer_password(db, datos.token, datos.nueva_password, info_cliente(request))


@router.post(
    "/password/cambiar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar mi contraseña (obligatorio si es temporal)",
)
def cambiar_password(datos: CambiarPasswordEntrada, ctx: ContextoBaseDep, db: DbDep) -> None:
    auth_service.cambiar_password(
        db, ctx.user, ctx.sesion, datos.password_actual, datos.nueva_password, ctx.cliente
    )
