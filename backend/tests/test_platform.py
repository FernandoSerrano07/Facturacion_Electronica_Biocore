"""Alta y administración de empresas por el SUPERADMIN (FLUJOS §3)."""

from sqlalchemy import select, text

from app.models.platform import AuditLog, Tenant, User
from tests.conftest import PASSWORD, PASSWORD_NUEVA, crear_usuario, headers, login


def test_crear_empresa_crea_schema_migrado_y_admin(client, db, token_superadmin) -> None:
    r = client.post(
        "/platform/tenants",
        headers=headers(token_superadmin),
        json={
            "slug": "Farmacia-San-Jose",
            "razon_social": "Farmacia San José, S.A. de C.V.",
            "nit": "0614-100590-101-1",
            "nrc": "123456-7",
            "plan": "enterprise",
            "admin": {
                "email": "Gerencia@Farmacia.example.com",
                "nombre": "Ana",
                "apellido": "López",
                "password_temporal": PASSWORD,
            },
        },
    )
    assert r.status_code == 201, r.text
    datos = r.json()
    tenant = datos["tenant"]
    assert tenant["slug"] == "farmacia-san-jose"
    assert tenant["nit"] == "06141005901011"
    assert tenant["nrc"] == "1234567"
    assert tenant["schema_name"] == "tenant_" + tenant["id"].replace("-", "")
    assert datos["admin"]["rol"] == "ADMIN_EMPRESA"
    assert datos["admin"]["email"] == "gerencia@farmacia.example.com"
    assert datos["admin"]["debe_cambiar_password"] is True

    version = db.execute(text(f'SELECT version_num FROM "{tenant["schema_name"]}".alembic_version')).scalar()
    assert version == "0001"

    # El ADMIN entra, cambia la contraseña temporal y llega a su panel
    sesion = login(client, "gerencia@farmacia.example.com")
    assert sesion["ruta_inicial"] == "/empresa"
    client.post(
        "/auth/password/cambiar",
        headers=headers(sesion["access_token"]),
        json={"password_actual": PASSWORD, "nueva_password": PASSWORD_NUEVA},
    )
    perfil = client.get("/auth/me", headers=headers(sesion["access_token"])).json()
    assert perfil["empresa"]["slug"] == "farmacia-san-jose"

    assert db.scalar(select(AuditLog).where(AuditLog.accion == "platform.tenant_creado")) is not None


def test_datos_duplicados_o_invalidos(client, crear_empresa, token_superadmin) -> None:
    crear_empresa(slug="tienda-abc", nit="06141005901011")
    base = {
        "razon_social": "Otra",
        "admin": {"email": "otro@example.com", "nombre": "A", "apellido": "B", "password_temporal": PASSWORD},
    }
    mismo_slug = client.post(
        "/platform/tenants", headers=headers(token_superadmin), json={**base, "slug": "tienda-abc"}
    )
    assert mismo_slug.status_code == 409
    mismo_nit = client.post(
        "/platform/tenants",
        headers=headers(token_superadmin),
        json={**base, "slug": "tienda-xyz", "nit": "0614-100590-101-1"},
    )
    assert mismo_nit.status_code == 409
    mismo_correo = client.post(
        "/platform/tenants",
        headers=headers(token_superadmin),
        json={
            **base,
            "slug": "tienda-xyz",
            "admin": {**base["admin"], "email": "admin@tienda-abc.example.com"},
        },
    )
    assert mismo_correo.status_code == 409
    for invalido in (
        {"slug": "Con Espacios"},
        {"slug": "ok-slug", "nit": "123"},
        {"slug": "ok", "plan": "gratis"},
    ):
        r = client.post("/platform/tenants", headers=headers(token_superadmin), json={**base, **invalido})
        assert r.status_code == 422, invalido


def test_solo_superadmin_gestiona_empresas(client, empresa) -> None:
    admin = headers(empresa["admin_token"])
    assert client.get("/platform/tenants", headers=admin).status_code == 403
    assert client.get("/platform/auditoria", headers=admin).status_code == 403
    assert (
        client.post(f"/platform/tenants/{empresa['tenant']['id']}/suspender", headers=admin).status_code
        == 403
    )


def test_suspender_bloquea_acceso_inmediato_y_reactivar(client, db, empresa, token_superadmin) -> None:
    tenant_id = empresa["tenant"]["id"]
    admin = headers(empresa["admin_token"])
    assert client.get("/empresa/usuarios", headers=admin).status_code == 200

    r = client.post(f"/platform/tenants/{tenant_id}/suspender", headers=headers(token_superadmin))
    assert r.status_code == 200 and r.json()["activo"] is False

    # El token emitido antes deja de servir y no puede volver a entrar
    assert client.get("/empresa/usuarios", headers=admin).status_code in (401, 403)
    rechazo = client.post("/auth/login", json={"email": empresa["admin_email"], "password": PASSWORD_NUEVA})
    assert rechazo.status_code == 403 and "inactiva" in rechazo.json()["detail"]

    # Los datos siguen ahí (no se borra nada)
    assert db.scalar(select(User).where(User.email == empresa["admin_email"])) is not None

    r = client.post(f"/platform/tenants/{tenant_id}/activar", headers=headers(token_superadmin))
    assert r.status_code == 200 and r.json()["activo"] is True
    login(client, empresa["admin_email"], PASSWORD_NUEVA)


def test_editar_y_listar_empresas(client, db, crear_empresa, token_superadmin) -> None:
    a = crear_empresa(slug="empresa-a")
    crear_empresa(slug="empresa-b")
    r = client.patch(
        f"/platform/tenants/{a['tenant']['id']}",
        headers=headers(token_superadmin),
        json={"plan": "free", "razon_social": "Empresa A Renombrada"},
    )
    assert r.status_code == 200
    assert r.json()["plan"] == "free" and r.json()["razon_social"] == "Empresa A Renombrada"
    assert (
        client.patch(
            f"/platform/tenants/{a['tenant']['id']}", headers=headers(token_superadmin), json={"plan": None}
        ).status_code
        == 422
    )

    lista = client.get("/platform/tenants", headers=headers(token_superadmin)).json()
    assert {t["slug"] for t in lista} == {"empresa-a", "empresa-b"}
    assert client.get("/platform/tenants/00000000-0000-0000-0000-000000000000",
                      headers=headers(token_superadmin)).status_code == 404  # fmt: skip


def test_auditoria_de_plataforma_filtra_por_empresa(client, crear_empresa, token_superadmin) -> None:
    a = crear_empresa(slug="empresa-a")
    crear_empresa(slug="empresa-b")
    r = client.get(
        "/platform/auditoria", headers=headers(token_superadmin), params={"tenant_id": a["tenant"]["id"]}
    )
    assert r.status_code == 200
    assert r.json() and all(e["tenant_id"] == a["tenant"]["id"] for e in r.json())


def test_superadmin_no_entra_al_panel_de_empresa(client, token_superadmin) -> None:
    assert client.get("/empresa/usuarios", headers=headers(token_superadmin)).status_code == 403


def test_falla_en_alta_no_deja_schema_huerfano(client, db, token_superadmin, monkeypatch) -> None:
    """Si algo falla a mitad del alta, la transacción completa (incluido el schema) se revierte."""
    from app.services import tenant_service

    def fallar(*args, **kwargs):
        raise RuntimeError("falla simulada después de crear el schema")

    monkeypatch.setattr(tenant_service, "hash_password", fallar)
    try:
        client.post(
            "/platform/tenants",
            headers=headers(token_superadmin),
            json={
                "slug": "empresa-rota",
                "razon_social": "Rota",
                "admin": {
                    "email": "rota@example.com",
                    "nombre": "A",
                    "apellido": "B",
                    "password_temporal": PASSWORD,
                },
            },
        )
    except RuntimeError:
        pass
    db.expire_all()
    assert db.scalar(select(Tenant).where(Tenant.slug == "empresa-rota")) is None
    schemas = db.execute(
        text("SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'tenant\\_%'")
    ).scalar()
    assert schemas == 0


def test_crear_superadmin_por_cli_es_idempotente(db, monkeypatch, capsys) -> None:
    from app import cli
    from app.config import get_settings

    monkeypatch.setenv("SUPERADMIN_EMAIL", "Dueño@Example.com")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", PASSWORD)
    get_settings.cache_clear()
    try:
        assert cli.main(["crear-superadmin"]) == 0
        assert cli.main(["crear-superadmin"]) == 0
    finally:
        get_settings.cache_clear()
    db.expire_all()
    superadmins = db.scalars(select(User).where(User.rol == "SUPERADMIN")).all()
    assert len(superadmins) == 1
    assert superadmins[0].email == "dueño@example.com" and superadmins[0].debe_cambiar_password
    assert "Ya existe" in capsys.readouterr().out


def test_constraint_superadmin_sin_empresa(db, empresa) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        crear_usuario(db, email="raro@example.com", rol="SUPERADMIN", tenant_id=empresa["tenant"]["id"])
    db.rollback()
    with pytest.raises(IntegrityError):
        crear_usuario(db, email="huerfano@example.com", rol="CAJERO", tenant_id=None)
