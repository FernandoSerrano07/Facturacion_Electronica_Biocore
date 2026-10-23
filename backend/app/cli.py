"""Comandos de operación.

    python -m app.cli migrar            # schema platform + todos los schemas de empresa
    python -m app.cli crear-superadmin  # usa SUPERADMIN_EMAIL y SUPERADMIN_PASSWORD

`crear-superadmin` no hace nada si ya existe un SUPERADMIN: nunca sobrescribe una
contraseña existente. El SUPERADMIN creado debe cambiar su contraseña al primer ingreso.
"""

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import registrar
from app.core.permissions import Rol
from app.core.security import hash_password, validar_politica_password
from app.database import get_engine
from app.migraciones import migrar_platform, migrar_todos_los_tenants
from app.models.platform import User
from app.services.auth_service import normalizar_email


def migrar() -> int:
    migrar_platform()
    schemas = migrar_todos_los_tenants(get_engine())
    print(f"Migraciones aplicadas: platform + {len(schemas)} empresa(s)")
    return 0


def crear_superadmin() -> int:
    settings = get_settings()
    with Session(get_engine()) as db:
        if db.scalar(select(User.id).where(User.rol == Rol.SUPERADMIN.value).limit(1)) is not None:
            print("Ya existe un SUPERADMIN; no se hicieron cambios")
            return 0
        if not settings.superadmin_email or not settings.superadmin_password:
            print("SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD no definidos; se omite la creación")
            return 0

        password = settings.superadmin_password.get_secret_value()
        try:
            validar_politica_password(password)
        except ValueError as exc:
            print(f"SUPERADMIN_PASSWORD no cumple la política: {exc}", file=sys.stderr)
            return 1

        email = normalizar_email(settings.superadmin_email)
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            print(f"El correo {email} ya pertenece a otro usuario", file=sys.stderr)
            return 1

        user = User(
            tenant_id=None,
            email=email,
            hashed_password=hash_password(password),
            nombre="Super",
            apellido="Admin",
            rol=Rol.SUPERADMIN.value,
            debe_cambiar_password=True,
        )
        db.add(user)
        db.flush()
        registrar(
            db, accion="platform.superadmin_creado", modulo="platform", user_id=user.id, entidad_id=user.id
        )
        db.commit()
        print(f"SUPERADMIN creado: {email} (deberá cambiar la contraseña al ingresar)")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Operación de BIOCORE")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("migrar", help="Aplicar migraciones de platform y de todas las empresas")
    sub.add_parser("crear-superadmin", help="Crear el SUPERADMIN inicial desde variables de entorno")
    args = parser.parse_args(argv)
    if args.comando == "migrar":
        return migrar()
    return crear_superadmin()


if __name__ == "__main__":
    raise SystemExit(main())
