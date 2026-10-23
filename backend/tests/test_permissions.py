import pytest

from app.core.permissions import (
    MATRIZ_PERMISOS,
    RUTA_INICIAL,
    Acceso,
    Accion,
    Modulo,
    Rol,
    nivel_acceso,
    tiene_permiso,
)


def test_matriz_completa_para_todos_los_roles_y_modulos() -> None:
    for rol in Rol:
        assert set(MATRIZ_PERMISOS[rol]) == set(Modulo), rol
        assert rol in RUTA_INICIAL


@pytest.mark.parametrize(
    ("rol", "modulo", "esperado"),
    [
        (Rol.SUPERADMIN, Modulo.GESTION_TENANTS, Acceso.ESCRITURA),
        (Rol.ADMIN_EMPRESA, Modulo.GESTION_TENANTS, Acceso.NINGUNO),
        (Rol.ADMIN_EMPRESA, Modulo.CONFIG_DTE, Acceso.ESCRITURA),
        (Rol.GERENTE, Modulo.USUARIOS, Acceso.LECTURA),
        (Rol.GERENTE, Modulo.CONFIG_DTE, Acceso.NINGUNO),
        (Rol.SUBGERENTE, Modulo.ANULAR_VENTA, Acceso.CON_AUTORIZACION),
        (Rol.SUBGERENTE, Modulo.CXP, Acceso.CON_AUTORIZACION),
        (Rol.CAJERO, Modulo.POS, Acceso.ESCRITURA),
        (Rol.CAJERO, Modulo.PRODUCTOS, Acceso.LECTURA),
        (Rol.CAJERO, Modulo.INVENTARIO, Acceso.NINGUNO),
        (Rol.VENDEDOR, Modulo.CLIENTES, Acceso.ESCRITURA),
        (Rol.VENDEDOR, Modulo.CAJA, Acceso.NINGUNO),
        (Rol.CONTADOR, Modulo.LIBRO_IVA, Acceso.ESCRITURA),
        (Rol.CONTADOR, Modulo.POS, Acceso.NINGUNO),
        (Rol.BODEGUERO, Modulo.AJUSTE_INVENTARIO, Acceso.CON_AUTORIZACION),
        (Rol.BODEGUERO, Modulo.PRODUCTOS, Acceso.ESCRITURA),
        (Rol.BODEGUERO, Modulo.REPORTES_AVANZADOS, Acceso.NINGUNO),
    ],
)
def test_matriz_coincide_con_prd(rol: Rol, modulo: Modulo, esperado: Acceso) -> None:
    assert nivel_acceso(rol, modulo) is esperado


def test_auditor_nunca_escribe() -> None:
    for modulo in Modulo:
        assert not tiene_permiso(Rol.AUDITOR, modulo, Accion.ESCRIBIR)
    assert tiene_permiso(Rol.AUDITOR, Modulo.AUDITORIA, Accion.LEER)
    assert tiene_permiso(Rol.AUDITOR, Modulo.REPORTES_AVANZADOS, Accion.LEER)
    assert not tiene_permiso(Rol.AUDITOR, Modulo.ANULAR_VENTA, Accion.LEER)


def test_supervisor_caja_hereda_permisos_de_cajero() -> None:
    assert MATRIZ_PERMISOS[Rol.SUPERVISOR_CAJA] == MATRIZ_PERMISOS[Rol.CAJERO]


def test_acciones_segun_nivel() -> None:
    # ⚠️ permite solicitar, no ejecutar directamente
    assert tiene_permiso(Rol.SUBGERENTE, Modulo.ANULAR_VENTA, Accion.SOLICITAR)
    assert not tiene_permiso(Rol.SUBGERENTE, Modulo.ANULAR_VENTA, Accion.ESCRIBIR)
    # 👁 permite leer, no solicitar ni escribir
    assert tiene_permiso(Rol.GERENTE, Modulo.USUARIOS, Accion.LEER)
    assert not tiene_permiso(Rol.GERENTE, Modulo.USUARIOS, Accion.SOLICITAR)
    assert not tiene_permiso(Rol.GERENTE, Modulo.USUARIOS, Accion.ESCRIBIR)
    # ❌ no permite nada
    assert not tiene_permiso(Rol.CAJERO, Modulo.USUARIOS, Accion.LEER)
