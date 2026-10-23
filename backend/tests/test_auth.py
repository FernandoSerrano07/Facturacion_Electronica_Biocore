"""Flujo de autenticación (FLUJOS §2) contra PostgreSQL real."""

import time
from datetime import timedelta

import pyotp
from sqlalchemy import select

from app.core.security import ahora
from app.models.platform import AuditLog, PasswordResetToken, User, UserSession
from app.routers.auth import COOKIE_REFRESH
from tests.conftest import PASSWORD, PASSWORD_NUEVA, crear_usuario, headers, login, token


def test_login_exitoso_entrega_tokens_y_registra_auditoria(client, db, superadmin) -> None:
    respuesta = client.post(
        "/auth/login",
        json={"email": "ROOT@example.com", "password": PASSWORD},
        headers={"user-agent": "pytest-navegador"},
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["requiere_2fa"] is False
    assert datos["token_type"] == "bearer"
    assert datos["expires_in"] == 15 * 60
    assert datos["ruta_inicial"] == "/platform"
    assert datos["usuario"]["rol"] == "SUPERADMIN"

    cookie = respuesta.headers["set-cookie"]
    assert COOKIE_REFRESH in cookie and "HttpOnly" in cookie and "Path=/auth" in cookie
    assert "refresh_token" not in datos  # el refresh solo viaja en la cookie

    perfil = client.get("/auth/me", headers=headers(datos["access_token"]))
    assert perfil.status_code == 200
    assert perfil.json()["permisos"]["gestion_tenants"] == "escritura"

    db.expire_all()
    evento = db.scalar(select(AuditLog).where(AuditLog.accion == "auth.login_exitoso"))
    assert evento is not None and evento.user_agent == "pytest-navegador"
    assert db.get(User, superadmin.id).ultimo_login is not None


def test_credenciales_invalidas_no_revelan_si_el_correo_existe(client, superadmin) -> None:
    inexistente = client.post("/auth/login", json={"email": "nadie@example.com", "password": PASSWORD})
    incorrecta = client.post("/auth/login", json={"email": superadmin.email, "password": "mala-clave-123"})
    assert inexistente.status_code == incorrecta.status_code == 401
    assert inexistente.json() == incorrecta.json()


def test_bloqueo_tras_cinco_intentos_y_aviso_por_correo(client, db, superadmin, correos) -> None:
    for intento in range(4):
        r = client.post("/auth/login", json={"email": superadmin.email, "password": "mala-clave-123"})
        assert r.status_code == 401, intento
    quinto = client.post("/auth/login", json={"email": superadmin.email, "password": "mala-clave-123"})
    assert quinto.status_code == 423
    assert len(correos) == 1 and "bloqueada" in correos[0].asunto

    # Ni con la contraseña correcta entra mientras dure el bloqueo
    correcta = client.post("/auth/login", json={"email": superadmin.email, "password": PASSWORD})
    assert correcta.status_code == 423

    db.expire_all()
    user = db.get(User, superadmin.id)
    assert user.bloqueado_hasta is not None and user.bloqueado_hasta > ahora()

    # Al vencer el bloqueo vuelve a entrar y el contador queda en cero
    user.bloqueado_hasta = ahora() - timedelta(seconds=1)
    db.commit()
    login(client, superadmin.email)
    db.expire_all()
    assert db.get(User, superadmin.id).intentos_fallidos == 0


def test_usuario_inactivo_no_puede_entrar(client, db, superadmin) -> None:
    superadmin.activo = False
    db.commit()
    r = client.post("/auth/login", json={"email": superadmin.email, "password": PASSWORD})
    assert r.status_code == 403


def test_refresh_rota_el_token_y_detecta_reutilizacion(client, db, superadmin) -> None:
    login(client, superadmin.email)
    primer_refresh = client.cookies.get(COOKIE_REFRESH)

    renovado = client.post("/auth/refresh")
    assert renovado.status_code == 200
    nuevo_access = renovado.json()["access_token"]
    segundo_refresh = client.cookies.get(COOKIE_REFRESH)
    assert segundo_refresh and segundo_refresh != primer_refresh
    assert client.get("/auth/me", headers=headers(nuevo_access)).status_code == 200

    # Alguien reutiliza el refresh viejo: se revoca la sesión completa
    client.cookies.set(COOKIE_REFRESH, primer_refresh, path="/auth")
    robado = client.post("/auth/refresh")
    assert robado.status_code == 401
    client.cookies.set(COOKIE_REFRESH, segundo_refresh, path="/auth")
    assert client.post("/auth/refresh").status_code == 401
    assert client.get("/auth/me", headers=headers(nuevo_access)).status_code == 401

    db.expire_all()
    assert db.scalar(select(AuditLog).where(AuditLog.accion == "auth.refresh_reutilizado")) is not None


def test_refresh_sin_cookie_o_basura(client) -> None:
    assert client.post("/auth/refresh").status_code == 401
    client.cookies.set(COOKIE_REFRESH, "basura", path="/auth")
    assert client.post("/auth/refresh").status_code == 401


def test_logout_revoca_la_sesion(client, superadmin) -> None:
    access = token(client, superadmin.email)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me", headers=headers(access)).status_code == 401
    assert client.post("/auth/refresh").status_code == 401
    # Idempotente
    assert client.post("/auth/logout").status_code == 204


def test_sesiones_activas_listar_y_cerrar_otra(client, nuevo_cliente, superadmin) -> None:
    access_pc = token(client, superadmin.email)
    celular = nuevo_cliente()
    access_celular = token(celular, superadmin.email)

    sesiones = client.get("/auth/sesiones", headers=headers(access_pc)).json()
    assert len(sesiones) == 2
    assert sum(s["actual"] for s in sesiones) == 1
    otra = next(s for s in sesiones if not s["actual"])

    assert client.delete(f"/auth/sesiones/{otra['id']}", headers=headers(access_pc)).status_code == 204
    assert celular.get("/auth/me", headers=headers(access_celular)).status_code == 401
    assert client.get("/auth/me", headers=headers(access_pc)).status_code == 200
    assert client.delete(f"/auth/sesiones/{otra['id']}", headers=headers(access_pc)).status_code == 404


def test_cerrar_otras_sesiones(client, nuevo_cliente, superadmin) -> None:
    access = token(client, superadmin.email)
    otros = [token(nuevo_cliente(), superadmin.email) for _ in range(2)]
    r = client.post("/auth/sesiones/cerrar-otras", headers=headers(access))
    assert r.status_code == 200 and "2" in r.json()["mensaje"]
    for access_otro in otros:
        assert client.get("/auth/me", headers=headers(access_otro)).status_code == 401
    assert client.get("/auth/me", headers=headers(access)).status_code == 200


def test_token_sin_bearer_o_invalido(client) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer no-es-jwt"}).status_code == 401


def _activar_2fa(client, access: str) -> tuple[str, int]:
    config = client.post("/auth/2fa/configurar", headers=headers(access))
    assert config.status_code == 200
    secreto = config.json()["secreto"]
    assert config.json()["otpauth_uri"].startswith("otpauth://totp/BIOCORE")
    activar = client.post(
        "/auth/2fa/activar", headers=headers(access), json={"codigo": pyotp.TOTP(secreto).now()}
    )
    assert activar.status_code == 204, activar.text
    return secreto, 30


def test_flujo_completo_2fa(client, db, superadmin) -> None:
    access = token(client, superadmin.email)
    secreto, periodo = _activar_2fa(client, access)

    db.expire_all()
    guardado = db.get(User, superadmin.id)
    assert guardado.totp_habilitado and secreto not in guardado.totp_secret  # cifrado en reposo

    desafio = client.post("/auth/login", json={"email": superadmin.email, "password": PASSWORD})
    assert desafio.status_code == 200
    assert desafio.json()["requiere_2fa"] is True
    assert "access_token" not in desafio.json()
    token_2fa = desafio.json()["token_2fa"]

    malo = client.post("/auth/login/2fa", json={"token_2fa": token_2fa, "codigo": "000000"})
    assert malo.status_code == 401

    # El código ya usado al activar no sirve: se usa el del siguiente período
    codigo = pyotp.TOTP(secreto).at(time.time() + periodo)
    bueno = client.post("/auth/login/2fa", json={"token_2fa": token_2fa, "codigo": codigo})
    assert bueno.status_code == 200, bueno.text
    nuevo_access = bueno.json()["access_token"]

    # Repetir el mismo código no funciona
    repetido = client.post("/auth/login/2fa", json={"token_2fa": token_2fa, "codigo": codigo})
    assert repetido.status_code == 401

    # Desactivar exige contraseña y un código nuevo
    sin_codigo_nuevo = client.post(
        "/auth/2fa/desactivar", headers=headers(nuevo_access), json={"password": PASSWORD, "codigo": codigo}
    )
    assert sin_codigo_nuevo.status_code == 400


def test_token_de_2fa_no_sirve_como_access(client, superadmin) -> None:
    access = token(client, superadmin.email)
    _activar_2fa(client, access)
    token_2fa = client.post("/auth/login", json={"email": superadmin.email, "password": PASSWORD}).json()[
        "token_2fa"
    ]
    assert client.get("/auth/me", headers=headers(token_2fa)).status_code == 401


def test_recuperacion_de_password_por_correo(client, db, superadmin, correos) -> None:
    access_viejo = token(client, superadmin.email)
    r = client.post("/auth/password/olvide", json={"email": superadmin.email})
    assert r.status_code == 202
    assert len(correos) == 1
    enlace = next(linea for linea in correos[0].texto.splitlines() if "token=" in linea)
    token_reset = enlace.split("token=", 1)[1].strip()

    # La respuesta es la misma para un correo inexistente, y no se envía nada
    r2 = client.post("/auth/password/olvide", json={"email": "nadie@example.com"})
    assert r2.status_code == 202 and r2.json() == r.json()
    assert len(correos) == 1

    restablecer = client.post(
        "/auth/password/restablecer", json={"token": token_reset, "nueva_password": PASSWORD_NUEVA}
    )
    assert restablecer.status_code == 204
    # Un solo uso
    again = client.post("/auth/password/restablecer", json={"token": token_reset, "nueva_password": PASSWORD})
    assert again.status_code == 400

    # Las sesiones anteriores quedaron cerradas y la nueva contraseña funciona
    assert client.get("/auth/me", headers=headers(access_viejo)).status_code == 401
    login(client, superadmin.email, PASSWORD_NUEVA)

    db.expire_all()
    guardados = db.scalars(select(PasswordResetToken)).all()
    assert len(guardados) == 1 and token_reset not in guardados[0].token_hash


def test_recuperacion_desbloquea_la_cuenta(client, db, superadmin, correos) -> None:
    superadmin.bloqueado_hasta = ahora() + timedelta(minutes=30)
    db.commit()
    client.post("/auth/password/olvide", json={"email": superadmin.email})
    token_reset = correos[-1].texto.split("token=", 1)[1].split()[0]
    client.post("/auth/password/restablecer", json={"token": token_reset, "nueva_password": PASSWORD_NUEVA})
    login(client, superadmin.email, PASSWORD_NUEVA)


def test_token_de_recuperacion_expirado(client, db, superadmin, correos) -> None:
    client.post("/auth/password/olvide", json={"email": superadmin.email})
    token_reset = correos[-1].texto.split("token=", 1)[1].split()[0]
    registro = db.scalar(select(PasswordResetToken))
    registro.expires_at = ahora() - timedelta(seconds=1)
    db.commit()
    r = client.post(
        "/auth/password/restablecer", json={"token": token_reset, "nueva_password": PASSWORD_NUEVA}
    )
    assert r.status_code == 400


def test_password_temporal_obliga_a_cambiarla(client, db, superadmin) -> None:
    crear_usuario(db, email="nuevo@example.com", rol="SUPERADMIN", debe_cambiar_password=True)
    datos = login(client, "nuevo@example.com")
    assert datos["usuario"]["debe_cambiar_password"] is True
    access = datos["access_token"]

    # /auth/me sí responde (el frontend necesita saberlo); lo demás no
    assert client.get("/auth/me", headers=headers(access)).status_code == 200
    assert client.get("/platform/tenants", headers=headers(access)).status_code == 403

    debil = client.post(
        "/auth/password/cambiar",
        headers=headers(access),
        json={"password_actual": PASSWORD, "nueva_password": "corta"},
    )
    assert debil.status_code == 422
    igual = client.post(
        "/auth/password/cambiar",
        headers=headers(access),
        json={"password_actual": PASSWORD, "nueva_password": PASSWORD},
    )
    assert igual.status_code == 400
    ok = client.post(
        "/auth/password/cambiar",
        headers=headers(access),
        json={"password_actual": PASSWORD, "nueva_password": PASSWORD_NUEVA},
    )
    assert ok.status_code == 204
    assert client.get("/platform/tenants", headers=headers(access)).status_code == 200


def test_cambiar_password_cierra_las_otras_sesiones(client, nuevo_cliente, db, superadmin) -> None:
    access = token(client, superadmin.email)
    otro = token(nuevo_cliente(), superadmin.email)
    r = client.post(
        "/auth/password/cambiar",
        headers=headers(access),
        json={"password_actual": PASSWORD, "nueva_password": PASSWORD_NUEVA},
    )
    assert r.status_code == 204
    assert client.get("/auth/me", headers=headers(otro)).status_code == 401
    assert client.get("/auth/me", headers=headers(access)).status_code == 200
    db.expire_all()
    activas = db.scalars(select(UserSession).where(UserSession.revocada_at.is_(None))).all()
    assert len(activas) == 1
