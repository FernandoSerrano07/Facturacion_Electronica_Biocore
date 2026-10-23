"""Punto de entrada HTTP del backend."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.errors import registrar_manejadores
from app.core.security import cifrado_disponible
from app.routers import auth, empresa, platform

logger = logging.getLogger("biocore")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="BIOCORE · Facturación Electrónica",
        version="0.2.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
    )

    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,  # necesario para la cookie del refresh token
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    registrar_manejadores(app)
    app.include_router(auth.router)
    app.include_router(platform.router)
    app.include_router(empresa.router)

    if not cifrado_disponible():
        logger.warning(
            "FERNET_KEY no configurada o inválida: la verificación en dos pasos no estará disponible"
        )

    @app.get("/health", tags=["Sistema"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "biocore-api"}

    return app


app = create_app()
