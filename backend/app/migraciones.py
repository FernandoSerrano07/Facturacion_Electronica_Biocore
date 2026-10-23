"""Ejecución programática de migraciones Alembic (platform y schemas de empresa)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, select

from app.core.tenant import validar_schema

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(seccion: str) -> Config:
    if seccion not in {"platform", "tenant"}:
        raise ValueError(f"Sección de migraciones desconocida: {seccion}")
    cfg = Config(str(BACKEND_DIR / "alembic.ini"), ini_section=seccion)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations" / seccion))
    return cfg


def migrar_platform(connection: Connection | None = None) -> None:
    cfg = alembic_config("platform")
    if connection is not None:
        cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


def migrar_tenant(connection: Connection, schema: str) -> None:
    """Crea (si falta) y migra un schema de empresa dentro de la transacción recibida."""
    cfg = alembic_config("tenant")
    cfg.attributes["connection"] = connection
    cfg.attributes["tenant_schema"] = validar_schema(schema)
    command.upgrade(cfg, "head")


def migrar_todos_los_tenants(engine: Engine) -> list[str]:
    """Migra cada schema de empresa en su propia transacción. Devuelve los schemas migrados."""
    from app.models.platform import Tenant

    with engine.connect() as conn:
        schemas = list(conn.execute(select(Tenant.schema_name).order_by(Tenant.created_at)).scalars())
    for schema in schemas:
        with engine.begin() as conn:
            migrar_tenant(conn, schema)
    return schemas
