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
