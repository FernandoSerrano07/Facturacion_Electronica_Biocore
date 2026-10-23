"""Configuración de pruebas.

Las pruebas que usan la base de datos necesitan PostgreSQL. Define TEST_DATABASE_URL con una
base de datos desechable cuyo nombre contenga "test" (se borran sus schemas en cada corrida):

    TEST_DATABASE_URL=postgresql+psycopg2://biocore:clave@localhost:5432/biocore_test python -m pytest

Sin esa variable, las pruebas de base de datos se omiten y el resto se ejecuta igual.
"""

import os

from cryptography.fernet import Fernet

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

os.environ.setdefault("ENVIRONMENT", "test")
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
else:
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "unit-test-placeholder-not-for-production")
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("BCRYPT_ROUNDS", "4")
os.environ["SMTP_HOST"] = ""  # nunca enviar correos reales desde las pruebas

import uuid  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

PASSWORD = "Clave-Segura-2026"
PASSWORD_NUEVA = "Otra-Clave-Segura-2026"


def _borrar_schemas_tenant(conn) -> None:
    schemas = conn.execute(
        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant\\_%'")
    ).scalars()
    for schema in list(schemas):
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if not TEST_DATABASE_URL:
        pytest.skip("Define TEST_DATABASE_URL para correr las pruebas con PostgreSQL")
    if "test" not in (make_url(TEST_DATABASE_URL).database or ""):
        pytest.exit("TEST_DATABASE_URL debe apuntar a una base de datos cuyo nombre contenga 'test'")

    from app.database import get_engine
    from app.migraciones import migrar_platform

    eng = get_engine()
    with eng.begin() as conn:
        _borrar_schemas_tenant(conn)
        conn.execute(text("DROP SCHEMA IF EXISTS platform CASCADE"))
    migrar_platform()
    yield eng
    eng.dispose()


@pytest.fixture
def db_limpia(engine: Engine) -> Engine:
    with engine.begin() as conn:
        _borrar_schemas_tenant(conn)
        conn.execute(
            text(
                "TRUNCATE platform.audit_log, platform.password_reset_tokens, platform.sessions, "
                "platform.users, platform.tenants RESTART IDENTITY CASCADE"
            )
        )
    return engine


@pytest.fixture
def db(db_limpia: Engine) -> Iterator[Session]:
    with Session(db_limpia, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client(db_limpia: Engine) -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture
def nuevo_cliente() -> Callable[[], TestClient]:
    """Otro navegador: comparte la app pero no las cookies."""
    from app.main import app

    return lambda: TestClient(app)


@pytest.fixture(autouse=True)
def correos(monkeypatch: pytest.MonkeyPatch) -> list:
    from app.services import email_service

    enviados: list = []
    monkeypatch.setattr(email_service, "enviar_correo", enviados.append)
    return enviados


def crear_usuario(
    db: Session,
    *,
    email: str,
    rol: str,
    tenant_id: uuid.UUID | None = None,
    password: str = PASSWORD,
    debe_cambiar_password: bool = False,
):
    from app.core.security import hash_password
    from app.models.platform import User

    user = User(
        email=email,
        rol=rol,
        tenant_id=tenant_id,
        hashed_password=hash_password(password),
        nombre="Prueba",
        apellido=rol.title(),
        debe_cambiar_password=debe_cambiar_password,
    )
    db.add(user)
    db.commit()
    return user


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    respuesta = client.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def token(client: TestClient, email: str, password: str = PASSWORD) -> str:
    return login(client, email, password)["access_token"]


@pytest.fixture
def superadmin(db: Session):
    return crear_usuario(db, email="root@example.com", rol="SUPERADMIN")


@pytest.fixture
def token_superadmin(client: TestClient, superadmin) -> str:
    return token(client, superadmin.email)


@pytest.fixture
def crear_empresa(client: TestClient, token_superadmin: str) -> Callable[..., dict]:
    """Da de alta una empresa vía API y deja al ADMIN con su contraseña definitiva."""

    def _crear(slug: str = "farmacia-san-jose", admin_email: str | None = None, **extra) -> dict:
        admin_email = admin_email or f"admin@{slug}.example.com"
        respuesta = client.post(
            "/platform/tenants",
            headers=headers(token_superadmin),
            json={
                "slug": slug,
                "razon_social": f"Empresa {slug}",
                "admin": {
                    "email": admin_email,
                    "nombre": "Ana",
                    "apellido": "Admin",
                    "password_temporal": PASSWORD,
                },
                **extra,
            },
        )
        assert respuesta.status_code == 201, respuesta.text
        datos = respuesta.json()
        temporal = token(client, admin_email)
        cambio = client.post(
            "/auth/password/cambiar",
            headers=headers(temporal),
            json={"password_actual": PASSWORD, "nueva_password": PASSWORD_NUEVA},
        )
        assert cambio.status_code == 204, cambio.text
        datos["admin_token"] = temporal
        datos["admin_email"] = admin_email
        return datos

    return _crear


@pytest.fixture
def empresa(crear_empresa) -> dict:
    return crear_empresa()
