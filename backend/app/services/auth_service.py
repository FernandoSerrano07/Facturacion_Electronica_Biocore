"""Flujos de autenticación (FLUJOS §2): login, 2FA, refresh, logout y contraseñas."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import InfoCliente, registrar
from app.core.errors import ErrorServicio
from app.core.security import (
    TIPO_2FA,
    TokenInvalido,
    ahora,
    cifrado_disponible,
    cifrar,
    crear_access_token,
    crear_token_2fa,
    decodificar_token,
    descifrar,
    generar_refresh_token,
    generar_secreto_totp,
    generar_token_recuperacion,
    hash_password,
    hash_token,
    separar_refresh_token,
    tokens_iguales,
    uri_totp,
    verificar_password,
    verificar_password_falsa,
    verificar_totp,
)
from app.models.platform import PasswordResetToken, Tenant, User, UserSession
from app.services.email_service import Correo, correo_bloqueo, correo_recuperacion

MODULO = "auth"
CREDENCIALES_INVALIDAS = "Correo o contraseña incorrectos"
SESION_INVALIDA = "La sesión no es válida o expiró. Inicia sesión de nuevo."
SEGUNDOS_ENTRE_RECUPERACIONES = 60


@dataclass
class SesionEmitida:
    user: User
    sesion: UserSession
    access_token: str
    expires_in: int
    refresh_token: str


@dataclass
class Desafio2FA:
    token: str
    expires_in: int


@dataclass
class ConfiguracionTotp:
    secreto: str
    uri: str


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def esta_bloqueado(user: User) -> bool:
    return user.bloqueado_hasta is not None and user.bloqueado_hasta > ahora()


def buscar_usuario_por_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalizar_email(email), User.deleted_at.is_(None)))


def revocar_sesiones(
    db: Session, user_id: uuid.UUID, motivo: str, *, excepto: uuid.UUID | None = None
) -> int:
    consulta = update(UserSession).where(UserSession.user_id == user_id, UserSession.revocada_at.is_(None))
    if excepto is not None:
        consulta = consulta.where(UserSession.id != excepto)
    resultado = db.execute(
        consulta.values(revocada_at=ahora(), motivo_revocacion=motivo),
        execution_options={"synchronize_session": False},
    )
    return resultado.rowcount or 0


# --- Login -----------------------------------------------------------------------


def _error_bloqueo() -> ErrorServicio:
    return ErrorServicio(
        423,
        "Cuenta bloqueada temporalmente por intentos fallidos. "
        "Restablece tu contraseña o contacta al administrador.",
    )


def _registrar_fallo(db: Session, user: User, cliente: InfoCliente, motivo: str) -> list[Correo]:
    """Suma un intento fallido y bloquea la cuenta al llegar al máximo (PRD §3.2)."""
    settings = get_settings()
    user.intentos_fallidos += 1
    registrar(
        db,
        accion="auth.login_fallido",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=user.tenant_id,
        user_id=user.id,
        detalle={"motivo": motivo, "intentos": user.intentos_fallidos},
    )
    correos: list[Correo] = []
    if user.intentos_fallidos >= settings.max_intentos_login:
        user.bloqueado_hasta = ahora() + timedelta(minutes=settings.bloqueo_minutos)
        user.intentos_fallidos = 0
        registrar(
            db,
            accion="auth.cuenta_bloqueada",
            modulo=MODULO,
            cliente=cliente,
            tenant_id=user.tenant_id,
            user_id=user.id,
            detalle={"hasta": user.bloqueado_hasta.isoformat()},
        )
        correos.append(correo_bloqueo(user.email, user.nombre, settings.bloqueo_minutos))
    db.commit()
    return correos


def _rechazar(db: Session, user: User, cliente: InfoCliente, motivo: str, error: ErrorServicio):
    registrar(
        db,
        accion="auth.login_rechazado",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=user.tenant_id,
        user_id=user.id,
        detalle={"motivo": motivo},
    )
    db.commit()
    raise error


def _validar_estado(db: Session, user: User, cliente: InfoCliente) -> None:
    """Usuario activo y empresa activa (FLUJOS §2: ¿Tiene empresa activa?)."""
    if not user.activo:
        _rechazar(db, user, cliente, "usuario_inactivo", ErrorServicio(403, "Usuario inactivo"))
    if user.tenant_id is not None:
        tenant = db.get(Tenant, user.tenant_id)
        if tenant is None or not tenant.activo:
            _rechazar(db, user, cliente, "empresa_inactiva", ErrorServicio(403, "La empresa está inactiva"))


def _emitir_sesion(db: Session, user: User, cliente: InfoCliente, metodo: str) -> SesionEmitida:
    settings = get_settings()
    sesion = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash="",
        ip=cliente.ip,
        user_agent=cliente.user_agent,
        expires_at=ahora() + timedelta(days=settings.refresh_token_expire_days),
    )
    refresh = generar_refresh_token(sesion.id)
    sesion.refresh_token_hash = hash_token(refresh)
    db.add(sesion)

    user.ultimo_login = ahora()
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None
    registrar(
        db,
        accion="auth.login_exitoso",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=user.tenant_id,
        user_id=user.id,
        entidad_id=sesion.id,
        detalle={"metodo": metodo},
    )
    db.commit()

    access, expira = crear_access_token(
        user_id=user.id, session_id=sesion.id, tenant_id=user.tenant_id, rol=user.rol
    )
    return SesionEmitida(user, sesion, access, expira, refresh)


def iniciar_sesion(
    db: Session, email: str, password: str, cliente: InfoCliente
) -> SesionEmitida | Desafio2FA:
    user = buscar_usuario_por_email(db, email)
    if user is None:
        verificar_password_falsa(password)
        registrar(
            db,
            accion="auth.login_fallido",
            modulo=MODULO,
            cliente=cliente,
            detalle={"motivo": "usuario_inexistente", "email": normalizar_email(email)[:200]},
        )
        db.commit()
        raise ErrorServicio(401, CREDENCIALES_INVALIDAS)

    if esta_bloqueado(user):
        _rechazar(db, user, cliente, "cuenta_bloqueada", _error_bloqueo())

    if not verificar_password(password, user.hashed_password):
        correos = _registrar_fallo(db, user, cliente, "password_incorrecta")
        if correos:
            raise ErrorServicio(423, _error_bloqueo().detalle, correos=correos)
        raise ErrorServicio(401, CREDENCIALES_INVALIDAS)

    _validar_estado(db, user, cliente)

    if user.totp_habilitado and user.totp_secret:
        token, expira = crear_token_2fa(user.id)
        return Desafio2FA(token=token, expires_in=expira)

    return _emitir_sesion(db, user, cliente, metodo="password")


def completar_2fa(db: Session, token_2fa: str, codigo: str, cliente: InfoCliente) -> SesionEmitida:
    try:
        payload = decodificar_token(token_2fa, TIPO_2FA)
    except TokenInvalido:
        raise ErrorServicio(401, "La verificación expiró. Inicia sesión de nuevo.") from None

    user = db.get(User, payload["sub"])
    if user is None or user.deleted_at is not None or not user.totp_habilitado or not user.totp_secret:
        raise ErrorServicio(401, "La verificación expiró. Inicia sesión de nuevo.")
    if esta_bloqueado(user):
        _rechazar(db, user, cliente, "cuenta_bloqueada", _error_bloqueo())

    contador = verificar_totp(descifrar(user.totp_secret), codigo, user.totp_ultimo_contador)
    if contador is None:
        correos = _registrar_fallo(db, user, cliente, "codigo_2fa_incorrecto")
        if correos:
            raise ErrorServicio(423, _error_bloqueo().detalle, correos=correos)
        raise ErrorServicio(401, "Código de verificación incorrecto")

    user.totp_ultimo_contador = contador
    _validar_estado(db, user, cliente)
    return _emitir_sesion(db, user, cliente, metodo="password+totp")


# --- Refresh y logout ---------------------------------------------------------------


def _sesion_desde_refresh(db: Session, refresh_token: str | None) -> UserSession | None:
    partes = separar_refresh_token(refresh_token) if refresh_token else None
    if partes is None:
        return None
    return db.get(UserSession, partes[0], with_for_update=True)


def renovar_sesion(db: Session, refresh_token: str | None, cliente: InfoCliente) -> SesionEmitida:
    """Rota el refresh token. Reusar uno ya rotado revoca la sesión (posible robo)."""
    settings = get_settings()
    sesion = _sesion_desde_refresh(db, refresh_token)
    if sesion is None or sesion.revocada_at is not None or sesion.expires_at <= ahora():
        raise ErrorServicio(401, SESION_INVALIDA)

    user = db.get(User, sesion.user_id)
    if not tokens_iguales(refresh_token or "", sesion.refresh_token_hash):
        sesion.revocada_at = ahora()
        sesion.motivo_revocacion = "refresh_reutilizado"
        registrar(
            db,
            accion="auth.refresh_reutilizado",
            modulo=MODULO,
            cliente=cliente,
            tenant_id=user.tenant_id if user else None,
            user_id=sesion.user_id,
            entidad_id=sesion.id,
        )
        db.commit()
        raise ErrorServicio(401, SESION_INVALIDA)

    if user is None or not user.activo or user.deleted_at is not None:
        raise ErrorServicio(401, SESION_INVALIDA)
    if user.tenant_id is not None:
        tenant = db.get(Tenant, user.tenant_id)
        if tenant is None or not tenant.activo:
            raise ErrorServicio(403, "La empresa está inactiva")

    nuevo = generar_refresh_token(sesion.id)
    sesion.refresh_token_hash = hash_token(nuevo)
    sesion.ultimo_uso_at = ahora()
    sesion.expires_at = ahora() + timedelta(days=settings.refresh_token_expire_days)
    db.commit()

    access, expira = crear_access_token(
        user_id=user.id, session_id=sesion.id, tenant_id=user.tenant_id, rol=user.rol
    )
    return SesionEmitida(user, sesion, access, expira, nuevo)


def cerrar_sesion(db: Session, refresh_token: str | None, cliente: InfoCliente) -> None:
    """Idempotente: si el token no corresponde a una sesión activa no hace nada."""
    sesion = _sesion_desde_refresh(db, refresh_token)
    if (
        sesion is None
        or sesion.revocada_at is not None
        or not tokens_iguales(refresh_token or "", sesion.refresh_token_hash)
    ):
        db.rollback()
        return
    sesion.revocada_at = ahora()
    sesion.motivo_revocacion = "logout"
    user = db.get(User, sesion.user_id)
    registrar(
        db,
        accion="auth.logout",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=user.tenant_id if user else None,
        user_id=sesion.user_id,
        entidad_id=sesion.id,
    )
    db.commit()


# --- Contraseñas --------------------------------------------------------------------


def solicitar_recuperacion(db: Session, email: str, cliente: InfoCliente) -> Correo | None:
    """Genera un token de un solo uso. Nunca revela si el correo existe."""
    settings = get_settings()
    user = buscar_usuario_por_email(db, email)
    if user is None or not user.activo:
        return None

    reciente = db.scalar(
        select(PasswordResetToken.id).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.usado_at.is_(None),
            PasswordResetToken.created_at > ahora() - timedelta(seconds=SEGUNDOS_ENTRE_RECUPERACIONES),
        )
    )
    if reciente is not None:
        return None

    # Solo el enlace más reciente sirve: los anteriores se invalidan.
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.usado_at.is_(None))
        .values(usado_at=ahora()),
        execution_options={"synchronize_session": False},
    )
    token = generar_token_recuperacion()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=ahora() + timedelta(minutes=settings.password_reset_expire_minutes),
            ip=cliente.ip,
        )
    )
    registrar(
        db,
        accion="auth.recuperacion_solicitada",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=user.tenant_id,
        user_id=user.id,
    )
    db.commit()
    return correo_recuperacion(user.email, user.nombre, token, settings.password_reset_expire_minutes)


def restablecer_password(db: Session, token: str, nueva: str, cliente: InfoCliente) -> None:
    registro = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)).with_for_update()
    )
    invalido = ErrorServicio(400, "El enlace de recuperación no es válido o ya expiró")
    if registro is None or registro.usado_at is not None or registro.expires_at <= ahora():
        raise invalido
    user = db.get(User, registro.user_id)
    if user is None or not user.activo or user.deleted_at is not None:
        raise invalido

    registro.usado_at = ahora()
    user.hashed_password = hash_password(nueva)
    user.debe_cambiar_password = False
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None  # desbloqueo por email (PRD §3.2)
    revocar_sesiones(db, user.id, "password_restablecido")
    registrar(
        db,
        accion="auth.password_restablecido",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=user.tenant_id,
        user_id=user.id,
    )
    db.commit()


def cambiar_password(
    db: Session, user: User, sesion_actual: UserSession, actual: str, nueva: str, cliente: InfoCliente
) -> None:
    if not verificar_password(actual, user.hashed_password):
        raise ErrorServicio(400, "La contraseña actual no es correcta")
    if verificar_password(nueva, user.hashed_password):
        raise ErrorServicio(400, "La nueva contraseña debe ser distinta de la actual")
    user.hashed_password = hash_password(nueva)
    user.debe_cambiar_password = False
    revocar_sesiones(db, user.id, "password_cambiado", excepto=sesion_actual.id)
    registrar(
        db,
        accion="auth.password_cambiado",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=user.tenant_id,
        user_id=user.id,
    )
    db.commit()


# --- 2FA ------------------------------------------------------------------------------


def configurar_2fa(db: Session, user: User) -> ConfiguracionTotp:
    if user.totp_habilitado:
        raise ErrorServicio(409, "La verificación en dos pasos ya está activada")
    if not cifrado_disponible():
        raise ErrorServicio(503, "La verificación en dos pasos no está disponible en este servidor")
    secreto = generar_secreto_totp()
    user.totp_secret = cifrar(secreto)
    user.totp_ultimo_contador = None
    db.commit()
    return ConfiguracionTotp(secreto=secreto, uri=uri_totp(secreto, user.email))


def activar_2fa(db: Session, user: User, codigo: str, cliente: InfoCliente) -> None:
    if user.totp_habilitado:
        raise ErrorServicio(409, "La verificación en dos pasos ya está activada")
    if not user.totp_secret:
        raise ErrorServicio(400, "Primero genera el código QR con /auth/2fa/configurar")
    contador = verificar_totp(descifrar(user.totp_secret), codigo, None)
    if contador is None:
        raise ErrorServicio(400, "Código de verificación incorrecto")
    user.totp_habilitado = True
    user.totp_ultimo_contador = contador
    registrar(
        db,
        accion="auth.2fa_activado",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=user.tenant_id,
        user_id=user.id,
    )
    db.commit()


def desactivar_2fa(db: Session, user: User, password: str, codigo: str, cliente: InfoCliente) -> None:
    if not user.totp_habilitado or not user.totp_secret:
        raise ErrorServicio(409, "La verificación en dos pasos no está activada")
    if not verificar_password(password, user.hashed_password):
        raise ErrorServicio(400, "La contraseña no es correcta")
    contador = verificar_totp(descifrar(user.totp_secret), codigo, user.totp_ultimo_contador)
    if contador is None:
        raise ErrorServicio(400, "Código de verificación incorrecto")
    user.totp_habilitado = False
    user.totp_secret = None
    user.totp_ultimo_contador = None
    registrar(
        db,
        accion="auth.2fa_desactivado",
        modulo=MODULO,
        cliente=cliente,
        tenant_id=user.tenant_id,
        user_id=user.id,
    )
    db.commit()
