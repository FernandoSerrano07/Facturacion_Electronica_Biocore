"""Registro de auditoría (PRD §3.14). Nunca guardar contraseñas, tokens ni secretos en `detalle`."""

import ipaddress
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.platform import AuditLog

_MAX_USER_AGENT = 500


@dataclass(frozen=True)
class InfoCliente:
    ip: str | None
    user_agent: str | None


def info_cliente(request: Request) -> InfoCliente:
    """IP y user-agent del cliente; la IP solo se guarda si es una dirección válida."""
    ip = request.client.host if request.client else None
    try:
        ip = str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        ip = None
    user_agent = request.headers.get("user-agent")
    return InfoCliente(ip=ip, user_agent=user_agent[:_MAX_USER_AGENT] if user_agent else None)


def registrar(
    db: Session,
    *,
    accion: str,
    modulo: str,
    cliente: InfoCliente | None = None,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    entidad_id: str | uuid.UUID | None = None,
    detalle: dict[str, Any] | None = None,
) -> AuditLog:
    """Agrega el registro a la sesión; quien llama decide cuándo hacer commit."""
    entrada = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        accion=accion,
        modulo=modulo,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        detalle=detalle,
        ip=cliente.ip if cliente else None,
        user_agent=cliente.user_agent if cliente else None,
    )
    db.add(entrada)
    return entrada
