"""Motor y sesiones de base de datos.

El motor se crea de forma diferida para que importar la aplicación no abra
conexiones (las pruebas sin base de datos siguen funcionando).
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.core import tenant as _tenant  # noqa: F401  (registra el listener de search_path)


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().sqlalchemy_database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Una sesión por petición; lo que no se confirme con `commit()` se descarta."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
