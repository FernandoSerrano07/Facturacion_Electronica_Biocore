"""Contraseñas (bcrypt), JWT (HS256), TOTP para 2FA y cifrado Fernet."""

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import bcrypt
import jwt
import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

ALGORITMO_JWT = "HS256"
TIPO_ACCESS = "access"
TIPO_2FA = "2fa"
MINUTOS_TOKEN_2FA = 5
EMISOR_TOTP = "BIOCORE"

PASSWORD_MIN_CARACTERES = 10
PASSWORD_MAX_BYTES = 72  # límite propio de bcrypt


class TokenInvalido(Exception):
    """El token no se pudo validar (firma, expiración, tipo o estructura)."""


class CifradoNoConfigurado(RuntimeError):
    """Falta FERNET_KEY en el entorno."""


def ahora() -> datetime:
    return datetime.now(UTC)


# --- Contraseñas -----------------------------------------------------------------


def validar_politica_password(password: str) -> str:
    if len(password) < PASSWORD_MIN_CARACTERES:
        raise ValueError(f"La contraseña debe tener al menos {PASSWORD_MIN_CARACTERES} caracteres")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(f"La contraseña no puede superar {PASSWORD_MAX_BYTES} bytes")
    if not password.strip():
        raise ValueError("La contraseña no puede estar vacía")
    return password


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verificar_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


@lru_cache
def _hash_falso() -> str:
    return hash_password(secrets.token_urlsafe(16))


def verificar_password_falsa(password: str) -> None:
    """Gasta el mismo tiempo que una verificación real cuando el usuario no existe."""
    verificar_password(password[:PASSWORD_MAX_BYTES], _hash_falso())


# --- JWT -------------------------------------------------------------------------


def _clave_jwt() -> str:
    return get_settings().secret_key.get_secret_value()


def crear_access_token(
    *, user_id: uuid.UUID, session_id: uuid.UUID, tenant_id: uuid.UUID | None, rol: str
) -> tuple[str, int]:
    minutos = get_settings().access_token_expire_minutes
    emitido = ahora()
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "tid": str(tenant_id) if tenant_id else None,
        "rol": rol,
        "typ": TIPO_ACCESS,
        "iat": emitido,
        "exp": emitido + timedelta(minutes=minutos),
    }
    return jwt.encode(payload, _clave_jwt(), algorithm=ALGORITMO_JWT), minutos * 60


def crear_token_2fa(user_id: uuid.UUID) -> tuple[str, int]:
    emitido = ahora()
    payload = {
        "sub": str(user_id),
        "typ": TIPO_2FA,
        "iat": emitido,
        "exp": emitido + timedelta(minutes=MINUTOS_TOKEN_2FA),
    }
    return jwt.encode(payload, _clave_jwt(), algorithm=ALGORITMO_JWT), MINUTOS_TOKEN_2FA * 60


def decodificar_token(token: str, tipo: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _clave_jwt(),
            algorithms=[ALGORITMO_JWT],
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenInvalido(str(exc)) from exc
    if payload.get("typ") != tipo:
        raise TokenInvalido("Tipo de token incorrecto")
    try:
        payload["sub"] = uuid.UUID(payload["sub"])
        if tipo == TIPO_ACCESS:
            payload["sid"] = uuid.UUID(payload["sid"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenInvalido("Token con estructura inválida") from exc
    return payload


# --- Tokens opacos (refresh y recuperación) ---------------------------------------


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_iguales(token: str, hash_guardado: str) -> bool:
    return hmac.compare_digest(hash_token(token), hash_guardado)


def generar_refresh_token(session_id: uuid.UUID) -> str:
    """Formato `<session_id>.<secreto>`: el id localiza la sesión, el secreto se compara por hash."""
    return f"{session_id}.{secrets.token_urlsafe(48)}"


def separar_refresh_token(token: str) -> tuple[uuid.UUID, str] | None:
    session_id, _, secreto = token.partition(".")
    if not secreto:
        return None
    try:
        return uuid.UUID(session_id), secreto
    except ValueError:
        return None


def generar_token_recuperacion() -> str:
    return secrets.token_urlsafe(32)


# --- TOTP (2FA) ------------------------------------------------------------------


def generar_secreto_totp() -> str:
    return pyotp.random_base32()


def uri_totp(secreto: str, email: str) -> str:
    return pyotp.TOTP(secreto).provisioning_uri(name=email, issuer_name=EMISOR_TOTP)


def verificar_totp(secreto: str, codigo: str, ultimo_contador: int | None) -> int | None:
    """Devuelve el contador usado si el código es válido y no fue usado antes.

    Acepta la ventana actual y una a cada lado (±30 s de desfase de reloj).
    Un código ya consumido (contador <= último usado) se rechaza para evitar repeticiones.
    """
    codigo = codigo.strip()
    if not (len(codigo) == 6 and codigo.isdigit()):
        return None
    totp = pyotp.TOTP(secreto)
    actual = totp.timecode(datetime.fromtimestamp(time.time(), UTC))
    for contador in (actual - 1, actual, actual + 1):
        if ultimo_contador is not None and contador <= ultimo_contador:
            continue
        if hmac.compare_digest(totp.generate_otp(contador), codigo):
            return contador
    return None


# --- Cifrado en reposo ------------------------------------------------------------


def _fernet() -> Fernet:
    clave = get_settings().fernet_key
    if clave is None:
        raise CifradoNoConfigurado("FERNET_KEY no está configurada")
    return Fernet(clave.get_secret_value().encode("ascii"))


def cifrado_disponible() -> bool:
    try:
        _fernet()
    except (CifradoNoConfigurado, ValueError):
        return False
    return True


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("No se pudo descifrar el valor (¿cambió FERNET_KEY?)") from exc
