"""Entorno Alembic del schema global `platform`."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool, text

from app.config import get_settings
from app.models import PlatformBase
from app.models.base import PLATFORM_SCHEMA

config = context.config
connection_externa: Connection | None = config.attributes.get("connection")

if config.config_file_name and connection_externa is None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = PlatformBase.metadata


def include_name(name, type_, parent_names) -> bool:
    if type_ == "schema":
        return name == PLATFORM_SCHEMA
    return True


def _ejecutar(connection: Connection) -> None:
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{PLATFORM_SCHEMA}"'))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=PLATFORM_SCHEMA,
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().sqlalchemy_database_url,
        target_metadata=target_metadata,
        version_table_schema=PLATFORM_SCHEMA,
        include_schemas=True,
        include_name=include_name,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if connection_externa is not None:
        _ejecutar(connection_externa)
        return
    engine = create_engine(get_settings().sqlalchemy_database_url, poolclass=pool.NullPool)
    with engine.begin() as connection:
        _ejecutar(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
