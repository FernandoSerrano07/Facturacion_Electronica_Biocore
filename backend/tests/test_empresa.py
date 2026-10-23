"""Gestión de usuarios dentro de una empresa, RBAC y aislamiento entre empresas."""

import pytest

from tests.conftest import PASSWORD, PASSWORD_NUEVA, headers, login, token


def _crear_usuario(client, admin_token: str, email: str, rol: str):
    return client.post(
        "/empresa/usuarios",
        headers=headers(admin_token),
        json={"email": email, "nombre": "Usu", "apellido": "Ario", "rol": rol, "password_temporal": PASSWORD},
    )


def _activar(client, email: str) -> str:
    """Primer ingreso: cambia la contraseña temporal y devuelve un access token útil."""
    access = token(client, email)
    r = client.post(
        "/auth/password/cambiar",
        headers=headers(access),
        json={"password_actual": PASSWORD, "nueva_password": PASSWORD_NUEVA},
    )
    assert r.status_code == 204
    return access


def test_admin_crea_usuarios_con_password_temporal(client, empresa) -> None:
    r = _crear_usuario(client, empresa["admin_token"], "Cajero1@Farmacia.example.com", "CAJERO")
    assert r.status_code == 201, r.text
    usuario = r.json()
    assert usuario["email"] == "cajero1@farmacia.example.com"
    assert usuario["tenant_id"] == empresa["tenant"]["id"]
    assert usuario["debe_cambiar_password"] is True

    sesion = login(client, "cajero1@farmacia.example.com")
    assert sesion["ruta_inicial"] == "/pos"
    assert (
        _crear_usuario(client, empresa["admin_token"], "cajero1@farmacia.example.com", "CAJERO").status_code
        == 409
    )


@pytest.mark.parametrize("rol", ["SUPERADMIN", "DUEÑO"])
def test_no_se_puede_asignar_rol_invalido(client, empresa, rol: str) -> None:
    assert _crear_usuario(client, empresa["admin_token"], "x@example.com", rol).status_code == 422


def test_matriz_rbac_en_usuarios(client, empresa) -> None:
    admin = empresa["admin_token"]
    for email, rol in [
        ("g@e.example.com", "GERENTE"),
        ("c@e.example.com", "CAJERO"),
        ("a@e.example.com", "AUDITOR"),
    ]:
        assert _crear_usuario(client, admin, email, rol).status_code == 201
    gerente = _activar(client, "g@e.example.com")
    cajero = _activar(client, "c@e.example.com")
    auditor = _activar(client, "a@e.example.com")

    # GERENTE y AUDITOR: 👁 solo lectura en Usuarios
    for lector in (gerente, auditor):
        assert client.get("/empresa/usuarios", headers=headers(lector)).status_code == 200
        assert _crear_usuario(client, lector, "z@e.example.com", "CAJERO").status_code == 403
    # CAJERO: ❌ sin acceso
    assert client.get("/empresa/usuarios", headers=headers(cajero)).status_code == 403
    # Auditoría: ADMIN y AUDITOR sí, GERENTE no
    assert client.get("/empresa/auditoria", headers=headers(admin)).status_code == 200
    assert client.get("/empresa/auditoria", headers=headers(auditor)).status_code == 200
    assert client.get("/empresa/auditoria", headers=headers(gerente)).status_code == 403


def test_aislamiento_entre_empresas(client, crear_empresa) -> None:
    a = crear_empresa(slug="farmacia-xyz")
    b = crear_empresa(slug="tienda-abc")
    usuario_b = _crear_usuario(client, b["admin_token"], "cajero@tienda.example.com", "CAJERO").json()

    lista_a = client.get("/empresa/usuarios", headers=headers(a["admin_token"])).json()
    assert {u["email"] for u in lista_a} == {a["admin_email"]}

    # Un usuario de otra empresa no existe para A: 404 en ver, editar, desbloquear, etc.
    ruta = f"/empresa/usuarios/{usuario_b['id']}"
    admin_a = headers(a["admin_token"])
    assert client.get(ruta, headers=admin_a).status_code == 404
    assert client.patch(ruta, headers=admin_a, json={"activo": False}).status_code == 404
    assert client.post(f"{ruta}/desbloquear", headers=admin_a).status_code == 404
    assert client.post(f"{ruta}/restablecer-password", headers=admin_a,
                       json={"password_temporal": PASSWORD}).status_code == 404  # fmt: skip

    auditoria_a = client.get("/empresa/auditoria", headers=admin_a).json()
    assert auditoria_a and all(e["tenant_id"] == a["tenant"]["id"] for e in auditoria_a)


def test_cambiar_rol_aplica_de_inmediato(client, empresa) -> None:
    admin = empresa["admin_token"]
    usuario = _crear_usuario(client, admin, "g@e.example.com", "GERENTE").json()
    gerente = _activar(client, "g@e.example.com")
    assert client.get("/empresa/usuarios", headers=headers(gerente)).status_code == 200

    r = client.patch(f"/empresa/usuarios/{usuario['id']}", headers=headers(admin), json={"rol": "CAJERO"})
    assert r.status_code == 200 and r.json()["rol"] == "CAJERO"
    # Mismo access token, pero el rol se lee de la base de datos
    assert client.get("/empresa/usuarios", headers=headers(gerente)).status_code == 403


def test_desactivar_usuario_cierra_sus_sesiones(client, empresa) -> None:
    admin = empresa["admin_token"]
    usuario = _crear_usuario(client, admin, "v@e.example.com", "VENDEDOR").json()
    vendedor = _activar(client, "v@e.example.com")

    r = client.patch(f"/empresa/usuarios/{usuario['id']}", headers=headers(admin), json={"activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False
    assert client.get("/auth/me", headers=headers(vendedor)).status_code == 401
    assert (
        client.post("/auth/login", json={"email": "v@e.example.com", "password": PASSWORD_NUEVA}).status_code
        == 403
    )


def test_admin_no_puede_quitarse_su_rol_ni_desactivarse(client, empresa) -> None:
    admin = empresa["admin_token"]
    yo = client.get("/auth/me", headers=headers(admin)).json()["usuario"]
    ruta = f"/empresa/usuarios/{yo['id']}"
    assert client.patch(ruta, headers=headers(admin), json={"rol": "CAJERO"}).status_code == 403
    assert client.patch(ruta, headers=headers(admin), json={"activo": False}).status_code == 403
    assert client.patch(ruta, headers=headers(admin), json={"nombre": "Ana María"}).status_code == 200


def test_desbloquear_y_password_temporal(client, empresa) -> None:
    admin = empresa["admin_token"]
    usuario = _crear_usuario(client, admin, "b@e.example.com", "BODEGUERO").json()
    for _ in range(5):
        client.post("/auth/login", json={"email": "b@e.example.com", "password": "mala-clave-123"})
    assert (
        client.post("/auth/login", json={"email": "b@e.example.com", "password": PASSWORD}).status_code == 423
    )

    r = client.post(f"/empresa/usuarios/{usuario['id']}/desbloquear", headers=headers(admin))
    assert r.status_code == 200 and r.json()["bloqueado_hasta"] is None
    assert login(client, "b@e.example.com")["ruta_inicial"] == "/inventario"

    r = client.post(
        f"/empresa/usuarios/{usuario['id']}/restablecer-password",
        headers=headers(admin),
        json={"password_temporal": "Temporal-Nueva-123"},
    )
    assert r.status_code == 200 and r.json()["debe_cambiar_password"] is True
    assert login(client, "b@e.example.com", "Temporal-Nueva-123")["usuario"]["debe_cambiar_password"] is True


def test_admin_quita_2fa_de_un_usuario(client, empresa) -> None:
    import pyotp

    admin = empresa["admin_token"]
    usuario = _crear_usuario(client, admin, "c@e.example.com", "CONTADOR").json()
    contador = _activar(client, "c@e.example.com")
    secreto = client.post("/auth/2fa/configurar", headers=headers(contador)).json()["secreto"]
    client.post("/auth/2fa/activar", headers=headers(contador), json={"codigo": pyotp.TOTP(secreto).now()})
    assert (
        client.post("/auth/login", json={"email": "c@e.example.com", "password": PASSWORD_NUEVA}).json()[
            "requiere_2fa"
        ]
        is True
    )

    r = client.post(f"/empresa/usuarios/{usuario['id']}/desactivar-2fa", headers=headers(admin))
    assert r.status_code == 200 and r.json()["totp_habilitado"] is False
    assert login(client, "c@e.example.com", PASSWORD_NUEVA)["requiere_2fa"] is False
