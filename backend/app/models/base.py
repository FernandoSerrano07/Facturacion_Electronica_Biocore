"""Bases declarativas: una para el schema `platform` y otra para los schemas de empresa."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

PLATFORM_SCHEMA = "platform"


class PlatformBase(DeclarativeBase):
    """Tablas globales del SaaS (tenants, usuarios, sesiones, auditoría)."""

    metadata = MetaData(schema=PLATFORM_SCHEMA, naming_convention=NAMING_CONVENTION)


class TenantBase(DeclarativeBase):
    """Tablas de cada empresa. Sin schema fijo: se resuelven con el search_path."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
