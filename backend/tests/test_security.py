import time
import uuid
from datetime import timedelta

import jwt
import pyotp
import pytest

from app.config import get_settings
from app.core import security
from app.core.security import (
    TIPO_2FA,
    TIPO_ACCESS,
    TokenInvalido,
    crear_access_token,
    crear_token_2fa,
    decodificar_token,
)


def test_hash_y_verificacion_de_password() -> None:
    hashed = security.hash_password("Clave-Segura-2026")
    assert hashed != "Clave-Segura-2026"
    assert security.verificar_password("Clave-Segura-2026", hashed)
    assert not security.verificar_password("otra-clave-123", hashed)
    assert not security.verificar_password("x", "hash-corrupto")


@pytest.mark.parametrize("password", ["corta", "a" * 9, "ñ" * 37, " " * 12])
def test_politica_de_password_rechaza(password: str) -> None:
    with pytest.raises(ValueError):
        security.validar_politica_password(password)


def test_access_token_ida_y_vuelta() -> None:
    user_id, session_id, tenant_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token, expira = crear_access_token(
        user_id=user_id, session_id=session_id, tenant_id=tenant_id, rol="CAJERO"
    )
    payload = decodificar_token(token, TIPO_ACCESS)
    assert payload["sub"] == user_id
    assert payload["sid"] == session_id
    assert payload["tid"] == str(tenant_id)
    assert expira == get_settings().access_token_expire_minutes * 60


def test_token_de_otro_tipo_se_rechaza() -> None:
    token_2fa, _ = crear_token_2fa(uuid.uuid4())
    with pytest.raises(TokenInvalido):
        decodificar_token(token_2fa, TIPO_ACCESS)
    decodificar_token(token_2fa, TIPO_2FA)


def test_token_expirado_o_alterado_se_rechaza() -> None:
    clave = get_settings().secret_key.get_secret_value()
    pasado = security.ahora() - timedelta(minutes=30)
    expirado = jwt.encode(
        {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "typ": TIPO_ACCESS, "iat": pasado,
         "exp": pasado + timedelta(minutes=15)},
        clave,
        algorithm="HS256",
    )  # fmt: skip
    with pytest.raises(TokenInvalido):
        decodificar_token(expirado, TIPO_ACCESS)

    falso = jwt.encode(
        {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "typ": TIPO_ACCESS, "iat": security.ahora(),
         "exp": security.ahora() + timedelta(minutes=5)},
        "otra-clave-que-no-es-la-del-servidor",
        algorithm="HS256",
    )  # fmt: skip
    with pytest.raises(TokenInvalido):
        decodificar_token(falso, TIPO_ACCESS)

    sin_firma = jwt.encode(
        {"sub": str(uuid.uuid4()), "typ": TIPO_ACCESS, "iat": security.ahora(),
         "exp": security.ahora() + timedelta(minutes=5)},
        None,
        algorithm="none",
    )  # fmt: skip
    with pytest.raises(TokenInvalido):
        decodificar_token(sin_firma, TIPO_ACCESS)


def test_refresh_token_formato() -> None:
    session_id = uuid.uuid4()
    token = security.generar_refresh_token(session_id)
    assert security.separar_refresh_token(token) == (session_id, token.split(".", 1)[1])
    assert security.tokens_iguales(token, security.hash_token(token))
    assert security.separar_refresh_token("basura") is None
    assert security.separar_refresh_token("no-es-uuid.secreto") is None


def test_totp_valido_y_sin_repeticion() -> None:
    secreto = security.generar_secreto_totp()
    codigo = pyotp.TOTP(secreto).now()
    contador = security.verificar_totp(secreto, codigo, None)
    assert contador is not None
    # El mismo código no se acepta dos veces
    assert security.verificar_totp(secreto, codigo, contador) is None
    # El siguiente período sí
    siguiente = pyotp.TOTP(secreto).at(time.time() + 30)
    assert security.verificar_totp(secreto, siguiente, contador) == contador + 1
    assert security.verificar_totp(secreto, "12345", None) is None
    assert security.verificar_totp(secreto, "abcdef", None) is None


def test_cifrado_fernet() -> None:
    cifrado = security.cifrar("JBSWY3DPEHPK3PXP")
    assert cifrado != "JBSWY3DPEHPK3PXP"
    assert security.descifrar(cifrado) == "JBSWY3DPEHPK3PXP"
    with pytest.raises(ValueError):
        security.descifrar("no-es-un-token-fernet")
