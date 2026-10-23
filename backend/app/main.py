"""Punto de entrada HTTP del backend."""

from fastapi import FastAPI

from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="BIOCORE · Facturación Electrónica",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )

    @app.get("/health", tags=["Sistema"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "biocore-api"}

    return app


app = create_app()
