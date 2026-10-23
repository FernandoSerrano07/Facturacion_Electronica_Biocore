"""Construcción segura de nombres de schemas PostgreSQL.

Un identificador de empresa jamás debe concatenarse directamente desde un JWT.
La selección de schema pertenece a la transacción de la sesión autenticada.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def tenant_schema(tenant_id: str | UUID) -> str:
    """Convierte un UUID validado en un identificador SQL acotado y seguro."""
    parsed = UUID(str(tenant_id))
    return f"tenant_{parsed.hex}"


def set_tenant_schema(session: Session, tenant_id: str | UUID) -> None:
    """Selecciona el schema solo para la transacción SQL actual.

    Llamar después de validar JWT, estado del tenant y permisos RBAC.
    No invocar con nombres de schema proporcionados por el cliente.
    """
    schema = tenant_schema(tenant_id)
    session.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
