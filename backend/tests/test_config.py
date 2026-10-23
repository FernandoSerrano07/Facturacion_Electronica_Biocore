import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("postgres://u:p@host:5432/db", "postgresql+psycopg2://u:p@host:5432/db"),
        ("postgresql://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
        ("postgresql+psycopg2://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
    ],
)
def test_url_de_render_usa_psycopg2(entrada: str, esperado: str) -> None:
    settings = Settings(database_url=entrada, secret_key="x" * 40)
    assert settings.sqlalchemy_database_url == esperado


def test_produccion_exige_secret_key_larga() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", database_url="postgresql://h/db", secret_key="corta")


def test_cookie_segura_solo_en_produccion() -> None:
    assert Settings(
        environment="production", database_url="postgresql://h/db", secret_key="x" * 40
    ).cookie_secure
    assert not Settings(environment="test", database_url="postgresql://h/db", secret_key="x").cookie_secure


def test_cors_origins_separados_por_coma() -> None:
    settings = Settings(
        database_url="postgresql://h/db", secret_key="x", cors_origins=" https://a.com, ,https://b.com"
    )
    assert settings.cors_origins_list == ["https://a.com", "https://b.com"]
