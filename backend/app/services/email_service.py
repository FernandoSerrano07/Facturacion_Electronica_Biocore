"""Envío de correos transaccionales por SMTP.

Se ejecuta en segundo plano (BackgroundTasks). Un fallo de SMTP se registra en el log
y no interrumpe la petición. Sin SMTP configurado:
- en desarrollo/pruebas el correo completo se escribe en el log para poder probar;
- en producción solo se registra un error, sin el contenido (puede llevar enlaces privados).
"""

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("biocore.email")


@dataclass(frozen=True)
class Correo:
    destinatario: str
    asunto: str
    texto: str


def enviar_correo(correo: Correo) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        if settings.environment == "production":
            logger.error("SMTP no configurado: no se envió '%s' a %s", correo.asunto, correo.destinatario)
        else:
            logger.warning(
                "SMTP no configurado (%s). Correo para %s — %s\n%s",
                settings.environment,
                correo.destinatario,
                correo.asunto,
                correo.texto,
            )
        return

    mensaje = EmailMessage()
    mensaje["From"] = settings.smtp_from or settings.smtp_user or "no-reply@biocore.local"
    mensaje["To"] = correo.destinatario
    mensaje["Subject"] = correo.asunto
    mensaje.set_content(correo.texto)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
            smtp.send_message(mensaje)
    except (smtplib.SMTPException, OSError):
        logger.exception("No se pudo enviar '%s' a %s", correo.asunto, correo.destinatario)


def correo_recuperacion(destinatario: str, nombre: str | None, token: str, minutos: int) -> Correo:
    enlace = f"{get_settings().frontend_url.rstrip('/')}/restablecer-password?token={token}"
    return Correo(
        destinatario=destinatario,
        asunto="BIOCORE · Recupera tu contraseña",
        texto=(
            f"Hola {nombre or ''},\n\n"
            "Recibimos una solicitud para restablecer tu contraseña.\n"
            f"Abre este enlace (válido {minutos} minutos y de un solo uso):\n\n{enlace}\n\n"
            "Si no fuiste tú, ignora este correo; tu contraseña no cambiará.\n"
        ),
    )


def correo_bloqueo(destinatario: str, nombre: str | None, minutos: int) -> Correo:
    enlace = f"{get_settings().frontend_url.rstrip('/')}/recuperar-password"
    return Correo(
        destinatario=destinatario,
        asunto="BIOCORE · Tu cuenta fue bloqueada temporalmente",
        texto=(
            f"Hola {nombre or ''},\n\n"
            "Detectamos varios intentos fallidos de inicio de sesión en tu cuenta, "
            f"así que la bloqueamos por {minutos} minutos.\n\n"
            f"Para desbloquearla ahora, restablece tu contraseña aquí:\n{enlace}\n\n"
            "También puedes pedirle al administrador de tu empresa que la desbloquee.\n"
            "Si no fuiste tú, te recomendamos cambiar tu contraseña.\n"
        ),
    )
