from uuid import UUID

import pytest

from app.core.tenant import tenant_schema

UUID_VALIDO = "123e4567-e89b-12d3-a456-426614174000"


def test_tenant_schema_from_uuid() -> None:
    expected = "tenant_123e4567e89b12d3a456426614174000"
    assert tenant_schema(UUID_VALIDO) == expected
    assert tenant_schema(UUID(UUID_VALIDO)) == expected


@pytest.mark.parametrize("unsafe", ["foo", "1; DROP SCHEMA platform;", "", "tenant_123"])
def test_tenant_schema_rejects_invalid_identifiers(unsafe: str) -> None:
    with pytest.raises(ValueError):
        tenant_schema(unsafe)


@pytest.mark.parametrize("unsafe", ["public", "platform", 'tenant_x"; DROP', "tenant_" + "A" * 32])
def test_validar_schema_rechaza_nombres_no_canonicos(unsafe: str) -> None:
    from app.core.tenant import validar_schema

    with pytest.raises(ValueError):
        validar_schema(unsafe)


def test_search_path_por_empresa_se_mantiene_tras_commit_y_aisla_datos(db, crear_empresa) -> None:
    """Cada empresa ve solo su schema, incluso después de varios commits en la misma sesión."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.core.tenant import set_tenant_schema

    a = crear_empresa(slug="empresa-a")["tenant"]
    b = crear_empresa(slug="empresa-b")["tenant"]
    for tenant in (a, b):
        db.execute(text(f'CREATE TABLE "{tenant["schema_name"]}".notas (texto text)'))
        db.execute(text(f"INSERT INTO \"{tenant['schema_name']}\".notas VALUES ('{tenant['slug']}')"))
    db.commit()

    with Session(db.get_bind()) as sesion:
        set_tenant_schema(sesion, a["id"])
        assert sesion.execute(text("SELECT texto FROM notas")).scalars().all() == ["empresa-a"]
        sesion.commit()
        # Nueva transacción: el listener vuelve a aplicar SET LOCAL
        assert sesion.execute(text("SELECT texto FROM notas")).scalars().all() == ["empresa-a"]
        assert sesion.execute(text("SHOW search_path")).scalar() == f"{a['schema_name']}, public"

    with Session(db.get_bind()) as sesion:
        set_tenant_schema(sesion, b["id"])
        assert sesion.execute(text("SELECT texto FROM notas")).scalars().all() == ["empresa-b"]

    # Una sesión sin empresa no ve tablas de ninguna (el SET LOCAL no se filtra por el pool)
    with Session(db.get_bind()) as sesion:
        assert sesion.execute(text("SHOW search_path")).scalar() == '"$user", public'


def test_migraciones_coinciden_con_modelos(engine) -> None:
    """Equivale a `alembic --name platform check`: falla si un modelo cambió sin migración."""
    from alembic import command

    from app.migraciones import alembic_config

    command.check(alembic_config("platform"))
