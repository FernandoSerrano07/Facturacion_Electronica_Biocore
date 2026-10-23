"""Construcción segura de nombres de schemas PostgreSQL y selección por transacción.

Un identificador de empresa jamás debe concatenarse directamente desde un JWT.
El UUID del tenant se toma de `platform.tenants` después de validar el token,
y el schema se selecciona con `SET LOCAL`, que solo dura la transacción actual.
"""

import re
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.orm import Session

_PATRON_SCHEMA = re.compile(r"^tenant_[0-9a-f]{32}$")
_CLAVE_SCHEMA = "tenant_schema"


def tenant_schema(tenant_id: str | UUID) -> str:
    """Convierte un UUID validado en un identificador SQL acotado y seguro."""
    parsed = UUID(str(tenant_id))
    return f"tenant_{parsed.hex}"


def validar_schema(schema: str) -> str:
    """Rechaza cualquier nombre que no tenga la forma exacta `tenant_<32 hex>`."""
    if not _PATRON_SCHEMA.fullmatch(schema):
        raise ValueError(f"Nombre de schema de empresa inválido: {schema!r}")
    return schema


def set_tenant_schema(session: Session, tenant_id: str | UUID) -> None:
    """Fija el schema de la empresa para todas las transacciones de esta sesión.

    Llamar después de validar JWT, estado del tenant y permisos RBAC.
    No invocar con nombres de schema proporcionados por el cliente.
    El `SET LOCAL` se vuelve a aplicar al iniciar cada transacción, así el
    aislamiento se mantiene aunque el código haga `commit()` a mitad de la petición.
    """
    schema = tenant_schema(tenant_id)
    session.info[_CLAVE_SCHEMA] = schema
    if session.in_transaction():
        session.execute(text(f'SET LOCAL search_path TO "{schema}", public'))


def schema_actual(session: Session) -> str | None:
    return session.info.get(_CLAVE_SCHEMA)


@event.listens_for(Session, "after_begin")
def _aplicar_search_path(session: Session, transaction, connection) -> None:
    schema = session.info.get(_CLAVE_SCHEMA)
    if schema:
        validar_schema(schema)
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
