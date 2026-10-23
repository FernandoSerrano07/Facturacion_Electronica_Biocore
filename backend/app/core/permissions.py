"""Roles y matriz de permisos RBAC (PRD §5).

La matriz se transcribe tal cual del PRD para poder compararla a simple vista.
Reglas adicionales documentadas en docs/DECISIONES.md:

- AUDITOR es "solo lectura": cualquier ✅ de su columna se limita a lectura.
- SUPERVISOR_CAJA aparece en la jerarquía pero no en la matriz; mientras se define,
  recibe exactamente los permisos de CAJERO.
"""

from enum import IntEnum, StrEnum


class Rol(StrEnum):
    SUPERADMIN = "SUPERADMIN"
    ADMIN_EMPRESA = "ADMIN_EMPRESA"
    GERENTE = "GERENTE"
    SUBGERENTE = "SUBGERENTE"
    SUPERVISOR_CAJA = "SUPERVISOR_CAJA"
    CAJERO = "CAJERO"
    VENDEDOR = "VENDEDOR"
    CONTADOR = "CONTADOR"
    BODEGUERO = "BODEGUERO"
    AUDITOR = "AUDITOR"


ROLES_EMPRESA: tuple[Rol, ...] = tuple(rol for rol in Rol if rol is not Rol.SUPERADMIN)


class Modulo(StrEnum):
    GESTION_TENANTS = "gestion_tenants"
    CONFIG_EMPRESA = "config_empresa"
    CONFIG_DTE = "config_dte"
    USUARIOS = "usuarios"
    POS = "pos"
    ANULAR_VENTA = "anular_venta"
    CLIENTES = "clientes"
    PRODUCTOS = "productos"
    INVENTARIO = "inventario"
    AJUSTE_INVENTARIO = "ajuste_inventario"
    COMPRAS = "compras"
    CXC = "cxc"
    CXP = "cxp"
    CAJA = "caja"
    REPORTES_BASICOS = "reportes_basicos"
    REPORTES_AVANZADOS = "reportes_avanzados"
    LIBRO_IVA = "libro_iva"
    AUDITORIA = "auditoria"


class Acceso(IntEnum):
    NINGUNO = 0  # ❌
    LECTURA = 1  # 👁
    CON_AUTORIZACION = 2  # ⚠️ puede solicitar; un nivel superior aprueba
    ESCRITURA = 3  # ✅


class Accion(StrEnum):
    LEER = "leer"
    SOLICITAR = "solicitar"
    ESCRIBIR = "escribir"


_SIMBOLOS = {"✅": Acceso.ESCRITURA, "👁": Acceso.LECTURA, "⚠️": Acceso.CON_AUTORIZACION, "❌": Acceso.NINGUNO}

_COLUMNAS = (
    Rol.SUPERADMIN,
    Rol.ADMIN_EMPRESA,
    Rol.GERENTE,
    Rol.SUBGERENTE,
    Rol.CAJERO,
    Rol.VENDEDOR,
    Rol.CONTADOR,
    Rol.BODEGUERO,
    Rol.AUDITOR,
)

# Columnas:                        SUPERADMIN ADMIN GERENTE SUBGERENTE CAJERO VENDEDOR CONTADOR BODEGUERO AUDITOR
_MATRIZ_PRD: dict[Modulo, str] = {
    Modulo.GESTION_TENANTS:    "✅ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌",
    Modulo.CONFIG_EMPRESA:     "✅ ✅ 👁 ❌ ❌ ❌ 👁 ❌ 👁",
    Modulo.CONFIG_DTE:         "✅ ✅ ❌ ❌ ❌ ❌ ❌ ❌ ❌",
    Modulo.USUARIOS:           "✅ ✅ 👁 ❌ ❌ ❌ ❌ ❌ 👁",
    Modulo.POS:                "✅ ✅ ✅ ✅ ✅ ✅ ❌ ❌ 👁",
    Modulo.ANULAR_VENTA:       "✅ ✅ ✅ ⚠️ ❌ ❌ ❌ ❌ ❌",
    Modulo.CLIENTES:           "✅ ✅ ✅ ✅ 👁 ✅ 👁 ❌ 👁",
    Modulo.PRODUCTOS:          "✅ ✅ ✅ ✅ 👁 👁 👁 ✅ 👁",
    Modulo.INVENTARIO:         "✅ ✅ ✅ ✅ ❌ ❌ 👁 ✅ 👁",
    Modulo.AJUSTE_INVENTARIO:  "✅ ✅ ✅ ⚠️ ❌ ❌ ❌ ⚠️ ❌",
    Modulo.COMPRAS:            "✅ ✅ ✅ ✅ ❌ ❌ 👁 ✅ 👁",
    Modulo.CXC:                "✅ ✅ ✅ ✅ ❌ 👁 ✅ ❌ 👁",
    Modulo.CXP:                "✅ ✅ ✅ ⚠️ ❌ ❌ ✅ ❌ 👁",
    Modulo.CAJA:               "✅ ✅ ✅ ✅ ✅ ❌ 👁 ❌ 👁",
    Modulo.REPORTES_BASICOS:   "✅ ✅ ✅ ✅ ❌ 👁 ✅ 👁 ✅",
    Modulo.REPORTES_AVANZADOS: "✅ ✅ ✅ ❌ ❌ ❌ ✅ ❌ ✅",
    Modulo.LIBRO_IVA:          "✅ ✅ 👁 ❌ ❌ ❌ ✅ ❌ 👁",
    Modulo.AUDITORIA:          "✅ ✅ ❌ ❌ ❌ ❌ ❌ ❌ ✅",
}  # fmt: skip


def _construir_matriz() -> dict[Rol, dict[Modulo, Acceso]]:
    matriz: dict[Rol, dict[Modulo, Acceso]] = {rol: {} for rol in Rol}
    for modulo, fila in _MATRIZ_PRD.items():
        simbolos = fila.split()
        if len(simbolos) != len(_COLUMNAS):
            raise ValueError(f"Fila de permisos incompleta para {modulo}")
        for rol, simbolo in zip(_COLUMNAS, simbolos, strict=True):
            acceso = _SIMBOLOS[simbolo]
            if rol is Rol.AUDITOR:
                acceso = min(acceso, Acceso.LECTURA)
            matriz[rol][modulo] = acceso
    matriz[Rol.SUPERVISOR_CAJA] = dict(matriz[Rol.CAJERO])
    return matriz


MATRIZ_PERMISOS: dict[Rol, dict[Modulo, Acceso]] = _construir_matriz()


def nivel_acceso(rol: Rol | str, modulo: Modulo) -> Acceso:
    return MATRIZ_PERMISOS[Rol(rol)].get(modulo, Acceso.NINGUNO)


def tiene_permiso(rol: Rol | str, modulo: Modulo, accion: Accion) -> bool:
    nivel = nivel_acceso(rol, modulo)
    if accion is Accion.LEER:
        return nivel >= Acceso.LECTURA
    if accion is Accion.SOLICITAR:
        return nivel >= Acceso.CON_AUTORIZACION
    return nivel >= Acceso.ESCRITURA


def permisos_de(rol: Rol | str) -> dict[str, str]:
    """Resumen legible para el frontend: módulo → nivel."""
    return {modulo.value: acceso.name.lower() for modulo, acceso in MATRIZ_PERMISOS[Rol(rol)].items()}


# Redirección inicial después del login (FLUJOS §2)
RUTA_INICIAL: dict[Rol, str] = {
    Rol.SUPERADMIN: "/platform",
    Rol.ADMIN_EMPRESA: "/empresa",
    Rol.GERENTE: "/dashboard",
    Rol.SUBGERENTE: "/dashboard",
    Rol.SUPERVISOR_CAJA: "/pos",
    Rol.CAJERO: "/pos",
    Rol.VENDEDOR: "/pos",
    Rol.CONTADOR: "/reportes",
    Rol.BODEGUERO: "/inventario",
    Rol.AUDITOR: "/reportes",
}
