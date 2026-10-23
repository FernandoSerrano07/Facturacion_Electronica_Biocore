"""Errores de negocio que se convierten en respuestas JSON `{"detail": ...}`.

Pueden llevar correos pendientes: el manejador los envía en segundo plano aunque la
respuesta sea un error (por ejemplo, el aviso de cuenta bloqueada tras el 5.º intento).
"""

from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

from app.services import email_service
from app.services.email_service import Correo


class ErrorServicio(Exception):
    def __init__(
        self,
        status_code: int,
        detalle: str,
        *,
        correos: Sequence[Correo] = (),
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detalle)
        self.status_code = status_code
        self.detalle = detalle
        self.correos = tuple(correos)
        self.headers = headers


def enviar_correos(correos: Sequence[Correo]) -> None:
    for correo in correos:
        email_service.enviar_correo(correo)


async def _manejar_error_servicio(request: Request, exc: ErrorServicio) -> JSONResponse:
    tarea = BackgroundTask(enviar_correos, exc.correos) if exc.correos else None
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detalle},
        headers=exc.headers,
        background=tarea,
    )


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(ErrorServicio, _manejar_error_servicio)
