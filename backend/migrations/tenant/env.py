"""Entorno Alembic de los schemas de empresa (`tenant_<uuid-hex>`).

Cada schema guarda su propia tabla `alembic_version`, así cada empresa puede
estar en una versión distinta durante un despliegue y migrarse de forma independiente.

Uso desde la línea de comandos (por ejemplo para autogenerar sobre un schema de prueba):
    alembic --name tenant -x schema=tenant_<uuid-hex> upgrade head
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool, text

from app.config import get_settings
from app.core.tenant import validar_schema
from app.models import TenantBase

config = context.config
connection_externa: Connection | None = config.attributes.get("connection")

if config.config_file_name and connection_externa is None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = TenantBase.metadata


def _schema() -> str:
    schema = config.attributes.get("tenant_schema") or context.get_x_argument(as_dictionary=True).get(
        "schema"
    )
    if not schema:
        raise RuntimeError("Indica el schema de empresa: -x schema=tenant_<uuid-hex>")
    return validar_schema(schema)


def _ejecutar(connection: Connection, schema: str) -> None:
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=schema,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    # Si la transacción es compartida (alta de empresa), devolver el search_path original.
    connection.execute(text("SET LOCAL search_path TO DEFAULT"))


def run_migrations_online() -> None:
    schema = _schema()
    if connection_externa is not None:
        _ejecutar(connection_externa, schema)
        return
    engine = create_engine(get_settings().sqlalchemy_database_url, poolclass=pool.NullPool)
    with engine.begin() as connection:
        _ejecutar(connection, schema)


if context.is_offline_mode():
    raise RuntimeError("Las migraciones de empresa no soportan modo offline")
run_migrations_online()
