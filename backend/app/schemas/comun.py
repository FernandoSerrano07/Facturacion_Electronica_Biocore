"""Tipos reutilizables para validar entradas."""

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.core.security import validar_politica_password

PasswordNueva = Annotated[
    str,
    Field(description="Mínimo 10 caracteres y máximo 72 bytes"),
    AfterValidator(validar_politica_password),
]

TextoCorto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def normalizar_nit(valor: str | None) -> str | None:
    """NIT de 14 dígitos o DUI de 9 (homologado como NIT). Se guarda sin guiones."""
    if valor is None or not valor.strip():
        return None
    digitos = re.sub(r"[\s-]", "", valor)
    if not re.fullmatch(r"\d{14}|\d{9}", digitos):
        raise ValueError("El NIT debe tener 14 dígitos (o 9 si es DUI), con o sin guiones")
    return digitos


def normalizar_nrc(valor: str | None) -> str | None:
    if valor is None or not valor.strip():
        return None
    digitos = re.sub(r"[\s-]", "", valor)
    if not re.fullmatch(r"\d{1,8}", digitos):
        raise ValueError("El NRC debe tener entre 1 y 8 dígitos")
    return digitos


Nit = Annotated[str | None, AfterValidator(normalizar_nit)]
Nrc = Annotated[str | None, AfterValidator(normalizar_nrc)]


class Mensaje(BaseModel):
    mensaje: str


class EsquemaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
