# PRD — Sistema de Facturación Electrónica El Salvador
**Versión:** 1.0  
**Fecha:** 2026-10-22  
**Stack:** Python (FastAPI) · PostgreSQL · Multi-tenant · DTE / MH El Salvador  

---

## 1. VISIÓN GENERAL

Sistema SaaS multi-tenant de facturación electrónica compatible con los Documentos Tributarios Electrónicos (DTE) del Ministerio de Hacienda de El Salvador (Ley de Firma Electrónica + FESPAD 2023). Diseñado para farmacias, tiendas de abarrote, distribuidoras, y cualquier negocio contribuyente. El operador del sistema (SuperAdmin) gestiona múltiples empresas (tenants) desde un panel central.

---

## 2. ARQUITECTURA MULTI-TENANT

```
┌─────────────────────────────────────────────────┐
│              PLATAFORMA CENTRAL                  │
│  (SuperAdmin — owner del software)              │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Empresa A│  │ Empresa B│  │ Empresa C│  ...  │
│  │(tenant_1)│  │(tenant_2)│  │(tenant_3)│      │
│  └──────────┘  └──────────┘  └──────────┘      │
└─────────────────────────────────────────────────┘
```

### Estrategia de aislamiento de datos
- **Schema por tenant en PostgreSQL**: cada empresa tiene su propio schema (`tenant_<id>`). Las tablas maestras (catálogos MH, departamentos SV) viven en el schema `public`.
- La tabla `tenants` y `users` global viven en el schema `platform`.
- Cada request lleva el `tenant_id` en el JWT; el ORM cambia el `search_path` automáticamente.

---

## 3. MÓDULOS DEL SISTEMA

### 3.1 MÓDULO 0 — Plataforma / SuperAdmin
| Función | Descripción |
|---------|-------------|
| Gestión de tenants | Crear, suspender, activar empresas |
| Planes y licencias | Asignar plan Free/Pro/Enterprise por tenant |
| Soporte técnico | Ver logs, auditoría, impersonar usuarios con token temporal |
| Facturación del SaaS | Cobro mensual a clientes del sistema |
| Actualizaciones | Deploy de nuevas versiones sin downtime |

### 3.2 MÓDULO 1 — Autenticación y Seguridad
| Función | Descripción |
|---------|-------------|
| Login multi-tenant | Email + contraseña → JWT (access 15 min + refresh 7 días) |
| 2FA opcional | TOTP (Google Authenticator) por usuario |
| Sesiones activas | Ver y cerrar sesiones desde otros dispositivos |
| Recuperación de contraseña | Email con token de 1 uso (expira 1 hora) |
| Auditoría de accesos | IP, user-agent, timestamp por cada login |
| Bloqueo por intentos fallidos | Bloqueo tras 5 intentos; desbloqueo por admin o email |
| Roles y permisos | RBAC granular (ver sección 5) |

### 3.3 MÓDULO 2 — Configuración de Empresa (por tenant)
| Función | Descripción |
|---------|-------------|
| Datos fiscales | NIT, NRC, nombre comercial, razón social, actividad económica |
| Establecimientos | Código MH, dirección, teléfono (múltiples sucursales) |
| Cajas / puntos de venta | Por establecimiento |
| Logo e imagen | Para documentos impresos y PDF |
| Certificado digital | Cargar certificado `.p12` para firma DTE (cifrado en reposo) |
| Configuración DTE | Ambiente pruebas / producción, NIT receptor MH |
| Numeración correlativa | Por tipo de DTE: CCF, FC, NC, ND, NR |
| Condiciones default | Forma de pago default, validez de oferta, condiciones |

### 3.4 MÓDULO 3 — Facturación Electrónica DTE
#### Tipos de DTE soportados
| Código MH | Tipo | Descripción |
|-----------|------|-------------|
| 01 | Factura de Consumidor Final (FC) | Para no contribuyentes |
| 03 | Crédito Fiscal (CCF) | Para contribuyentes con NIT/NRC |
| 04 | Nota de Remisión (NR) | Acompañamiento de mercadería |
| 05 | Nota de Crédito (NC) | Devoluciones, descuentos |
| 06 | Nota de Débito (ND) | Cargos adicionales |
| 14 | Factura de Sujeto Excluido (FSE) | Proveedores sin NRC |

#### Flujo de emisión DTE
```
1. Generar JSON según esquema MH (v1 o v2)
2. Firmar con certificado digital (PKCS#7 / XAdES)
3. Enviar a API del proveedor (Oyama / Edicom / Hacienda directo)
4. Recibir sello de recepción (UUID DTE)
5. Guardar JSON firmado + sello en BD
6. Generar PDF de representación gráfica
7. Enviar PDF al cliente (email opcional)
```

#### Endpoint de integración (configurable por tenant)
```python
# En company_config: proveedor DTE
DTE_PROVIDERS = {
    "oyama": "https://api.oyama.com.sv/v1/dte",
    "edicom": "https://sv.edicomgroup.com/api/dte",
    "mh_directo": "https://apitest.dtes.mh.gob.sv/fesf/v1"  # MH directo
}
```

#### Campos requeridos CCF (Crédito Fiscal)
```json
{
  "identificacion": {
    "version": 3,
    "ambiente": "00",  // 00=pruebas, 01=produccion
    "tipoDte": "03",
    "numeroControl": "DTE-03-CXXX-000000000000001",
    "codigoGeneracion": "UUID-v4",
    "tipoModelo": 1,
    "tipoOperacion": 1,
    "tipoContingencia": null,
    "fecEmi": "2026-10-22",
    "horEmi": "16:00:00",
    "tipoMoneda": "USD"
  },
  "emisor": { /* NIT, NRC, nombre, codActividad, ... */ },
  "receptor": { /* NIT, NRC, nombre, correo, ... */ },
  "cuerpoDocumento": [ /* items */ ],
  "resumen": { /* totales, tributos, IVA */ },
  "firma": "..."
}
```

### 3.5 MÓDULO 4 — Punto de Venta (POS)
| Función | Descripción |
|---------|-------------|
| Búsqueda de productos | Por código de barras, nombre, SKU |
| Scanner de código de barras | Input directo desde lector USB/Bluetooth |
| Carrito de venta | Agregar, editar cantidad, eliminar ítems |
| Descuentos | Por ítem o sobre el total (% o monto fijo) |
| Múltiples formas de pago | Efectivo, tarjeta, transferencia, crédito interno |
| Cálculo de cambio | Para pago en efectivo |
| Selección tipo DTE | FC o CCF según cliente |
| Datos del receptor | Búsqueda por NIT/NRC o ingreso manual |
| Impresión | Ticket 80mm (térmica) o carta/PDF |
| Apertura/cierre de caja | Control de efectivo por turno |
| Anulación de venta | Con autorización de nivel superior + envío NC al MH |

### 3.6 MÓDULO 5 — Clientes (CRM básico)
| Función | Descripción |
|---------|-------------|
| Ficha de cliente | NIT, NRC, razón social, dirección, teléfono, email |
| Clasificación | Contribuyente / consumidor final / sujeto excluido |
| Crédito interno | Límite de crédito, días de plazo, saldo pendiente |
| Historial de compras | Ventas emitidas por cliente |
| Estado de cuenta | Facturas pendientes y pagadas |

### 3.7 MÓDULO 6 — Productos e Inventario
| Función | Descripción |
|---------|-------------|
| Catálogo de productos | Código, nombre, descripción, unidad de medida |
| Categorías y marcas | Árbol de categorías multinivel |
| Precios | Precio de costo, precio de venta, múltiples listas de precio |
| IVA | Grabado 13%, exento, no sujeto (según código MH) |
| Código de barras | EAN-13, Code128, generación automática |
| Almacenes | Múltiples bodegas por sucursal |
| Stock actual | Cantidad disponible, cantidad mínima (alerta), máxima |
| Lotes y vencimientos | Para farmacias: control por lote, fecha de vencimiento |
| Trazabilidad | Número de serie por producto (electrónicos, etc.) |
| Foto del producto | Imagen para mostrar en POS |

### 3.8 MÓDULO 7 — Kardex (Movimientos de Inventario)
| Función | Descripción |
|---------|-------------|
| Kardex por producto | Vista cronológica: entradas, salidas, ajustes, saldo |
| Métodos de valuación | PEPS (FIFO), UEPS (LIFO), Costo Promedio |
| Entrada por compra | Vinculada a orden de compra o directa |
| Salida por venta | Descontada automáticamente al facturar |
| Ajuste de inventario | Físico vs sistema — requiere autorización |
| Traslado entre bodegas | Movimiento interno trazado |
| Devolución de venta | Entrada automática al anular/crear NC |
| Devolución a proveedor | Salida vinculada a nota de crédito proveedor |

### 3.9 MÓDULO 8 — Compras y Proveedores
| Función | Descripción |
|---------|-------------|
| Ficha de proveedor | NIT, NRC, nombre, dirección, contacto, cuenta bancaria |
| Órdenes de compra | Generación, aprobación, recepción parcial/total |
| Recepción de mercadería | Ingreso a bodega con actualización kardex |
| Registro de compras | IVA crédito fiscal, cuentas por pagar |
| Devolución a proveedor | ND o FSE según tipo de proveedor |
| Estado de cuenta proveedor | Facturas pendientes, pagos realizados |

### 3.10 MÓDULO 9 — Cuentas por Cobrar
| Función | Descripción |
|---------|-------------|
| Ventas al crédito | Registro de créditos internos |
| Abonos y cancelaciones | Registro de pagos parciales o totales |
| Estado de cuenta | Por cliente, por fecha, por vencimiento |
| Alertas de vencimiento | Notificación de facturas próximas a vencer |
| Reporte de morosidad | Clientes con saldo vencido |

### 3.11 MÓDULO 10 — Cuentas por Pagar
| Función | Descripción |
|---------|-------------|
| Registro de facturas proveedor | Vinculado a recepción de OC |
| Pagos a proveedores | Registro de egresos |
| Calendario de pagos | Próximos compromisos |
| Cheques y transferencias | Registro por forma de pago |

### 3.12 MÓDULO 11 — Caja y Tesorería
| Función | Descripción |
|---------|-------------|
| Apertura de caja | Monto inicial en efectivo por turno |
| Cierre de caja | Conteo, cuadre, diferencias |
| Ingresos no fiscales | Abonos recibidos en caja |
| Egresos de caja | Pagos menores, gastos |
| Arqueo de caja | Reporte de movimientos del turno |
| Múltiples cajas | Por sucursal |

### 3.13 MÓDULO 12 — Reportes y Estadísticas
| Reporte | Tipo |
|---------|------|
| Ventas por período | Diario, semanal, mensual, anual |
| Ventas por producto | Más vendidos, menos vendidos |
| Ventas por vendedor | Comisiones, productividad |
| Ventas por cliente | Historial |
| Libro de ventas IVA | Formato MH para declaración mensual |
| Libro de compras IVA | Formato MH |
| Inventario valorado | Existencias × costo actual |
| Kardex imprimible | Por producto o por bodega |
| Cuentas por cobrar aging | Por antigüedad 0-30, 31-60, 61-90, +90 días |
| Rentabilidad por producto | Margen bruto |
| Dashboard ejecutivo | KPIs en tiempo real |

### 3.14 MÓDULO 13 — Auditoría y Logs
| Función | Descripción |
|---------|-------------|
| Log de acciones | Quién hizo qué, cuándo, desde qué IP |
| Historial de DTEs | Todos los documentos emitidos con estado MH |
| Cambios de precio | Registro de modificaciones de precios |
| Ajustes de inventario | Con justificación y usuario responsable |
| Eliminaciones | Nada se borra físicamente (soft delete + log) |

---

## 4. BASE DE DATOS — ESQUEMA POSTGRESQL

### Schema `platform` (global del SaaS)
```sql
-- Tenants (empresas cliente)
CREATE TABLE platform.tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(50) UNIQUE NOT NULL,  -- "farmacia-san-jose"
    razon_social    VARCHAR(200) NOT NULL,
    nit             VARCHAR(20) UNIQUE,
    nrc             VARCHAR(20),
    plan            VARCHAR(20) DEFAULT 'pro',    -- free|pro|enterprise
    activo          BOOLEAN DEFAULT TRUE,
    schema_name     VARCHAR(63) NOT NULL,          -- "tenant_abc123"
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Usuarios globales
CREATE TABLE platform.users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID REFERENCES platform.tenants(id),
    email           VARCHAR(200) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    nombre          VARCHAR(100),
    apellido        VARCHAR(100),
    rol             VARCHAR(30) NOT NULL,          -- ver sección 5
    activo          BOOLEAN DEFAULT TRUE,
    totp_secret     VARCHAR(100),                  -- 2FA
    ultimo_login    TIMESTAMPTZ,
    intentos_fallidos INT DEFAULT 0,
    bloqueado_hasta TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Sesiones activas
CREATE TABLE platform.sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES platform.users(id),
    refresh_token   VARCHAR(500) NOT NULL,
    ip              INET,
    user_agent      TEXT,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Log de auditoría global
CREATE TABLE platform.audit_log (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   UUID,
    user_id     UUID,
    accion      VARCHAR(100),
    modulo      VARCHAR(50),
    entidad_id  VARCHAR(100),
    detalle     JSONB,
    ip          INET,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### Schema `tenant_<id>` (por empresa)
```sql
-- Establecimientos / sucursales
CREATE TABLE establecimientos (
    id              SERIAL PRIMARY KEY,
    codigo_mh       VARCHAR(4) NOT NULL,  -- "0001"
    nombre          VARCHAR(200),
    direccion       TEXT,
    municipio_id    INT,
    departamento_id INT,
    telefono        VARCHAR(20),
    activo          BOOLEAN DEFAULT TRUE
);

-- Cajas por establecimiento
CREATE TABLE cajas (
    id                  SERIAL PRIMARY KEY,
    establecimiento_id  INT REFERENCES establecimientos(id),
    codigo              VARCHAR(20) NOT NULL,
    nombre              VARCHAR(100),
    activo              BOOLEAN DEFAULT TRUE
);

-- Turnos de caja
CREATE TABLE turnos_caja (
    id              SERIAL PRIMARY KEY,
    caja_id         INT REFERENCES cajas(id),
    user_id         UUID NOT NULL,
    monto_apertura  NUMERIC(12,2),
    monto_cierre    NUMERIC(12,2),
    diferencia      NUMERIC(12,2),
    abierto_at      TIMESTAMPTZ DEFAULT NOW(),
    cerrado_at      TIMESTAMPTZ,
    activo          BOOLEAN DEFAULT TRUE
);

-- Categorías de productos
CREATE TABLE categorias (
    id          SERIAL PRIMARY KEY,
    parent_id   INT REFERENCES categorias(id),
    nombre      VARCHAR(150) NOT NULL,
    codigo      VARCHAR(20)
);

-- Unidades de medida
CREATE TABLE unidades_medida (
    id      SERIAL PRIMARY KEY,
    codigo  VARCHAR(10) NOT NULL,  -- "UNI", "KG", "LT", "CJA"
    nombre  VARCHAR(50)
);

-- Productos
CREATE TABLE productos (
    id                  SERIAL PRIMARY KEY,
    codigo              VARCHAR(50) UNIQUE NOT NULL,
    codigo_barras       VARCHAR(50),
    nombre              VARCHAR(200) NOT NULL,
    descripcion         TEXT,
    categoria_id        INT REFERENCES categorias(id),
    unidad_medida_id    INT REFERENCES unidades_medida(id),
    precio_costo        NUMERIC(12,4) DEFAULT 0,
    precio_venta        NUMERIC(12,4) NOT NULL,
    tipo_iva            VARCHAR(10) DEFAULT 'gravado',  -- gravado|exento|no_sujeto
    codigo_tributo_mh   VARCHAR(5),   -- "20" IVA, "C3" FOVIAL, etc.
    stock_minimo        NUMERIC(12,2) DEFAULT 0,
    stock_maximo        NUMERIC(12,2),
    activo              BOOLEAN DEFAULT TRUE,
    foto_url            VARCHAR(500),
    requiere_lote       BOOLEAN DEFAULT FALSE,
    requiere_serie      BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Bodegas / almacenes
CREATE TABLE bodegas (
    id                  SERIAL PRIMARY KEY,
    establecimiento_id  INT REFERENCES establecimientos(id),
    nombre              VARCHAR(100),
    es_principal        BOOLEAN DEFAULT FALSE
);

-- Inventario por bodega (saldos actuales)
CREATE TABLE inventario (
    id          SERIAL PRIMARY KEY,
    producto_id INT REFERENCES productos(id),
    bodega_id   INT REFERENCES bodegas(id),
    cantidad    NUMERIC(12,2) DEFAULT 0,
    costo_prom  NUMERIC(12,4) DEFAULT 0,
    UNIQUE(producto_id, bodega_id)
);

-- Lotes (para farmacias)
CREATE TABLE lotes (
    id              SERIAL PRIMARY KEY,
    producto_id     INT REFERENCES productos(id),
    bodega_id       INT REFERENCES bodegas(id),
    numero_lote     VARCHAR(100),
    fecha_vencimiento DATE,
    cantidad        NUMERIC(12,2) DEFAULT 0,
    activo          BOOLEAN DEFAULT TRUE
);

-- Clientes
CREATE TABLE clientes (
    id              SERIAL PRIMARY KEY,
    tipo            VARCHAR(20) NOT NULL,  -- contribuyente|consumidor|excluido
    nit             VARCHAR(20),
    nrc             VARCHAR(20),
    nombre          VARCHAR(200) NOT NULL,
    email           VARCHAR(200),
    telefono        VARCHAR(30),
    direccion       TEXT,
    municipio_id    INT,
    departamento_id INT,
    limite_credito  NUMERIC(12,2) DEFAULT 0,
    dias_credito    INT DEFAULT 0,
    activo          BOOLEAN DEFAULT TRUE
);

-- Proveedores
CREATE TABLE proveedores (
    id              SERIAL PRIMARY KEY,
    nit             VARCHAR(20),
    nrc             VARCHAR(20),
    nombre          VARCHAR(200) NOT NULL,
    email           VARCHAR(200),
    telefono        VARCHAR(30),
    direccion       TEXT,
    cuenta_bancaria VARCHAR(50),
    activo          BOOLEAN DEFAULT TRUE
);

-- Correlativosdx DTE
CREATE TABLE correlativos_dte (
    id              SERIAL PRIMARY KEY,
    tipo_dte        VARCHAR(5) NOT NULL,   -- "01","03","04","05","06","14"
    establecimiento_id INT REFERENCES establecimientos(id),
    caja_id         INT,
    ultimo_numero   BIGINT DEFAULT 0,
    UNIQUE(tipo_dte, establecimiento_id, caja_id)
);

-- Cabecera de ventas / DTE
CREATE TABLE ventas (
    id                  SERIAL PRIMARY KEY,
    uuid_dte            UUID UNIQUE,
    numero_control      VARCHAR(40),           -- DTE-03-C001-000000000000001
    tipo_dte            VARCHAR(5) NOT NULL,
    estado              VARCHAR(20) DEFAULT 'borrador',  -- borrador|enviado|aceptado|rechazado|anulado
    sello_recepcion     TEXT,                  -- respuesta del MH
    json_dte_firmado    TEXT,                  -- JSON completo firmado
    caja_id             INT REFERENCES cajas(id),
    turno_id            INT REFERENCES turnos_caja(id),
    user_id             UUID NOT NULL,
    cliente_id          INT REFERENCES clientes(id),
    fecha_emision       DATE NOT NULL,
    hora_emision        TIME NOT NULL,
    condicion_pago      VARCHAR(20),           -- contado|credito
    dias_credito        INT DEFAULT 0,
    subtotal_gravado    NUMERIC(12,2) DEFAULT 0,
    subtotal_exento     NUMERIC(12,2) DEFAULT 0,
    subtotal_no_sujeto  NUMERIC(12,2) DEFAULT 0,
    descuento_global    NUMERIC(12,2) DEFAULT 0,
    iva_percibido       NUMERIC(12,2) DEFAULT 0,
    total               NUMERIC(12,2) NOT NULL,
    pdf_url             VARCHAR(500),
    notas               TEXT,
    venta_origen_id     INT REFERENCES ventas(id),  -- para NC/ND
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Detalle de venta
CREATE TABLE venta_items (
    id              SERIAL PRIMARY KEY,
    venta_id        INT REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id     INT REFERENCES productos(id),
    lote_id         INT REFERENCES lotes(id),
    numero_item     INT NOT NULL,
    cantidad        NUMERIC(12,4) NOT NULL,
    precio_unitario NUMERIC(12,4) NOT NULL,
    descuento       NUMERIC(12,2) DEFAULT 0,
    tipo_iva        VARCHAR(10),
    monto_iva       NUMERIC(12,4) DEFAULT 0,
    subtotal        NUMERIC(12,4) NOT NULL
);

-- Pagos de venta (múltiples formas de pago)
CREATE TABLE venta_pagos (
    id          SERIAL PRIMARY KEY,
    venta_id    INT REFERENCES ventas(id),
    forma_pago  VARCHAR(20) NOT NULL,  -- efectivo|tarjeta|transferencia|credito
    monto       NUMERIC(12,2) NOT NULL,
    referencia  VARCHAR(100),          -- número de autorización tarjeta, etc.
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Kardex de inventario
CREATE TABLE kardex (
    id              BIGSERIAL PRIMARY KEY,
    producto_id     INT REFERENCES productos(id),
    bodega_id       INT REFERENCES bodegas(id),
    lote_id         INT REFERENCES lotes(id),
    tipo_movimiento VARCHAR(30) NOT NULL,  -- ver abajo
    documento_tipo  VARCHAR(30),           -- venta|compra|ajuste|traslado|devolucion
    documento_id    INT,
    fecha           DATE NOT NULL,
    hora            TIME,
    cantidad        NUMERIC(12,4) NOT NULL,  -- positivo=entrada, negativo=salida
    costo_unitario  NUMERIC(12,4),
    costo_total     NUMERIC(12,4),
    saldo_cantidad  NUMERIC(12,4),
    saldo_valor     NUMERIC(12,4),
    user_id         UUID,
    notas           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
-- tipos de movimiento: VENTA, DEVOLUCION_VENTA, COMPRA, DEVOLUCION_COMPRA,
--                      AJUSTE_POS, AJUSTE_NEG, TRASLADO_SALIDA, TRASLADO_ENTRADA

-- Órdenes de compra
CREATE TABLE ordenes_compra (
    id              SERIAL PRIMARY KEY,
    proveedor_id    INT REFERENCES proveedores(id),
    user_id         UUID NOT NULL,
    estado          VARCHAR(20) DEFAULT 'pendiente',  -- pendiente|aprobada|recibida_parcial|recibida|cancelada
    fecha_orden     DATE NOT NULL,
    fecha_entrega   DATE,
    subtotal        NUMERIC(12,2),
    iva             NUMERIC(12,2),
    total           NUMERIC(12,2),
    notas           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ordenes_compra_items (
    id              SERIAL PRIMARY KEY,
    orden_id        INT REFERENCES ordenes_compra(id),
    producto_id     INT REFERENCES productos(id),
    cantidad_pedida NUMERIC(12,4),
    cantidad_recibida NUMERIC(12,4) DEFAULT 0,
    precio_unitario NUMERIC(12,4),
    subtotal        NUMERIC(12,4)
);

-- Cuentas por cobrar
CREATE TABLE cuentas_cobrar (
    id              SERIAL PRIMARY KEY,
    venta_id        INT REFERENCES ventas(id),
    cliente_id      INT REFERENCES clientes(id),
    monto_original  NUMERIC(12,2),
    saldo           NUMERIC(12,2),
    fecha_vence     DATE,
    estado          VARCHAR(20) DEFAULT 'pendiente',  -- pendiente|pagada|vencida|parcial
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE cuentas_cobrar_abonos (
    id              SERIAL PRIMARY KEY,
    cuenta_id       INT REFERENCES cuentas_cobrar(id),
    monto           NUMERIC(12,2),
    forma_pago      VARCHAR(20),
    referencia      VARCHAR(100),
    user_id         UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Configuración DTE por tenant
CREATE TABLE config_dte (
    id                  SERIAL PRIMARY KEY,
    proveedor           VARCHAR(30),   -- oyama|edicom|mh_directo
    api_url             VARCHAR(300),
    api_key_cifrada     TEXT,          -- cifrado con Fernet
    ambiente            VARCHAR(5) DEFAULT '00',  -- 00=pruebas 01=produccion
    certificado_p12     TEXT,          -- base64 cifrado
    clave_certificado   TEXT,          -- cifrada
    nit_emisor          VARCHAR(20),
    activo              BOOLEAN DEFAULT TRUE
);
```

---

## 5. ROLES Y PERMISOS (RBAC)

### Jerarquía de roles
```
SUPERADMIN (plataforma)
    └── ADMIN_EMPRESA (por tenant)
            ├── GERENTE
            │     └── SUBGERENTE
            │           ├── SUPERVISOR_CAJA
            │           ├── VENDEDOR
            │           └── CAJERO
            ├── CONTADOR
            ├── BODEGUERO
            └── AUDITOR (solo lectura)
```

### Matriz de permisos por módulo
| Módulo | SUPERADMIN | ADMIN | GERENTE | SUBGERENTE | CAJERO | VENDEDOR | CONTADOR | BODEGUERO | AUDITOR |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Gestión tenants | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Config. empresa | ✅ | ✅ | 👁 | ❌ | ❌ | ❌ | 👁 | ❌ | 👁 |
| Config. DTE | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Usuarios | ✅ | ✅ | 👁 | ❌ | ❌ | ❌ | ❌ | ❌ | 👁 |
| POS / Venta | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | 👁 |
| Anular venta | ✅ | ✅ | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Clientes | ✅ | ✅ | ✅ | ✅ | 👁 | ✅ | 👁 | ❌ | 👁 |
| Productos | ✅ | ✅ | ✅ | ✅ | 👁 | 👁 | 👁 | ✅ | 👁 |
| Inventario/Kardex | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | 👁 | ✅ | 👁 |
| Ajuste inventario | ✅ | ✅ | ✅ | ⚠️ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| Compras | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | 👁 | ✅ | 👁 |
| Cuentas × cobrar | ✅ | ✅ | ✅ | ✅ | ❌ | 👁 | ✅ | ❌ | 👁 |
| Cuentas × pagar | ✅ | ✅ | ✅ | ⚠️ | ❌ | ❌ | ✅ | ❌ | 👁 |
| Caja / Arqueo | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 👁 | ❌ | 👁 |
| Reportes básicos | ✅ | ✅ | ✅ | ✅ | ❌ | 👁 | ✅ | 👁 | ✅ |
| Reportes avanzados | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| Libro IVA | ✅ | ✅ | 👁 | ❌ | ❌ | ❌ | ✅ | ❌ | 👁 |
| Auditoría / Logs | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

**Leyenda:** ✅ Lectura + Escritura | 👁 Solo lectura | ⚠️ Con autorización | ❌ Sin acceso

---

## 6. ESTRUCTURA DE DIRECTORIOS DEL PROYECTO

```
facturacion_sv/
│
├── app/
│   ├── main.py                    # FastAPI app, startup, CORS, routers
│   ├── config.py                  # Settings (pydantic-settings + .env)
│   ├── database.py                # Engine, sesiones, cambio de schema por tenant
│   │
│   ├── core/
│   │   ├── security.py            # JWT, hashing, 2FA TOTP
│   │   ├── permissions.py         # RBAC decoradores y dependencias
│   │   ├── tenant.py              # Middleware de tenant (set search_path)
│   │   └── audit.py               # Función log_audit()
│   │
│   ├── models/                    # SQLAlchemy ORM
│   │   ├── platform.py            # tenants, users, sessions, audit_log
│   │   ├── empresa.py             # establecimientos, cajas, config_dte
│   │   ├── productos.py           # productos, categorias, inventario, kardex
│   │   ├── ventas.py              # ventas, venta_items, venta_pagos
│   │   ├── compras.py             # proveedores, ordenes_compra
│   │   ├── clientes.py            # clientes, cuentas_cobrar
│   │   └── caja.py                # turnos_caja
│   │
│   ├── schemas/                   # Pydantic v2
│   │   ├── auth.py
│   │   ├── ventas.py
│   │   ├── productos.py
│   │   └── dte.py                 # Schemas JSON DTE según MH
│   │
│   ├── routers/
│   │   ├── auth.py                # /auth/login, /auth/refresh, /auth/logout
│   │   ├── platform.py            # /platform/tenants (SUPERADMIN)
│   │   ├── empresa.py             # /empresa/config, /empresa/usuarios
│   │   ├── pos.py                 # /pos/venta, /pos/caja
│   │   ├── productos.py           # /productos CRUD
│   │   ├── inventario.py          # /inventario/kardex, /inventario/ajuste
│   │   ├── compras.py             # /compras/ordenes, /compras/recepcion
│   │   ├── clientes.py            # /clientes CRUD
│   │   ├── cxc.py                 # /cxc (cuentas por cobrar)
│   │   ├── reportes.py            # /reportes/*
│   │   └── dte.py                 # /dte/emitir, /dte/anular, /dte/pdf
│   │
│   └── services/
│       ├── dte_service.py         # Lógica emisión DTE: generar JSON, firmar, enviar
│       ├── pdf_service.py         # Generación de PDF representación gráfica
│       ├── kardex_service.py      # Lógica FIFO/LIFO/Costo Promedio
│       ├── email_service.py       # Envío de comprobantes por email
│       └── tenant_service.py     # Crear schema nuevo, migraciones por tenant
│
├── alembic/                       # Migraciones de BD
│   ├── env.py                     # Configurado para multi-schema
│   └── versions/
│
├── tests/
│   ├── test_auth.py
│   ├── test_dte.py
│   └── test_inventario.py
│
├── .env.example
├── requirements.txt
├── docker-compose.yml
└── README.md
```

---

## 7. DEPENDENCIAS PRINCIPALES

```
# requirements.txt
fastapi==0.115.x
uvicorn[standard]==0.30.x
sqlalchemy==2.0.x
alembic==1.13.x
psycopg2-binary==2.9.x
pydantic==2.x
pydantic-settings==2.x
python-jose[cryptography]==3.3.x   # JWT
passlib[bcrypt]==1.7.x
pyotp==2.9.x                       # 2FA TOTP
cryptography==42.x                 # firma DTE, cifrado cert
reportlab==4.x                     # PDFs
qrcode==7.x                        # QR en documentos
httpx==0.27.x                      # cliente HTTP async para API DTE
python-multipart==0.0.x
redis==5.x                         # cache sesiones / rate limiting
celery==5.x                        # tareas async (envío email, reintento DTE)
pillow==10.x
python-dotenv==1.0.x
```

---

## 8. VARIABLES DE ENTORNO CRÍTICAS

```env
# .env.example
DATABASE_URL=postgresql://user:pass@localhost:5432/facturacion_sv
REDIS_URL=redis://localhost:6379/0

SECRET_KEY=<random-256-bit>
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Cifrado de certificados DTE
FERNET_KEY=<base64-32-bytes>

# Email
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<sendgrid-key>

# Storage PDFs (S3 compatible)
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=facturacion-sv-pdfs
S3_ACCESS_KEY=<key>
S3_SECRET_KEY=<secret>

# SuperAdmin inicial
SUPERADMIN_EMAIL=admin@tusistema.com
SUPERADMIN_PASSWORD=<cambiar-al-iniciar>

ENVIRONMENT=development  # development|production
```

---

## 9. INTEGRACIÓN DTE — GUÍA DE IMPLEMENTACIÓN

### 9.1 Estructura del servicio DTE
```python
# app/services/dte_service.py

class DTEService:
    def __init__(self, config: ConfigDTE):
        self.config = config
        self.client = httpx.AsyncClient()

    async def emitir_ccf(self, venta: Venta, db: Session) -> DTEResult:
        # 1. Generar número de control correlativo
        numero_control = self._generar_numero_control("03", venta.caja_id, db)
        # 2. Construir JSON DTE según esquema MH v3
        json_dte = self._construir_json_ccf(venta, numero_control)
        # 3. Firmar con certificado digital
        json_firmado = self._firmar_json(json_dte)
        # 4. Enviar al proveedor API
        resultado = await self._enviar_a_proveedor(json_firmado)
        # 5. Guardar respuesta
        return resultado

    def _construir_json_ccf(self, venta, numero_control) -> dict:
        return {
            "identificacion": { ... },
            "emisor": self._get_emisor(),
            "receptor": self._get_receptor(venta.cliente),
            "cuerpoDocumento": self._get_items(venta.items),
            "resumen": self._get_resumen(venta)
        }

    def _firmar_json(self, json_dte: dict) -> str:
        # Usar cryptography + certificado p12 descifrado
        ...

    async def _enviar_a_proveedor(self, json_firmado: str) -> dict:
        # POST al endpoint del proveedor configurado
        response = await self.client.post(
            self.config.api_url,
            headers={"Authorization": f"Bearer {self._decrypt_apikey()}"},
            json={"documento": json_firmado}
        )
        return response.json()
```

### 9.2 Ejemplo payload para Oyama (referencial)
```python
# Adaptable según documentación oficial del proveedor elegido
POST https://api.oyama.com.sv/v1/dte/emitir
Authorization: Bearer <api_key>
Content-Type: application/json

{
  "nit_emisor": "0614-100590-101-1",
  "tipo_documento": "03",
  "documento_firmado": "<JSON DTE en base64 o string firmado>"
}

# Respuesta exitosa:
{
  "selloRecepcion": "2024...",
  "codigoGeneracion": "UUID",
  "estado": "PROCESADO",
  "fhProcesamiento": "2026-10-22T16:00:00"
}
```

---

## 10. CONSIDERACIONES DE SEGURIDAD

1. **Certificados DTE**: Cifrados en BD con Fernet (clave en variable de entorno). Nunca en texto plano.
2. **API Keys de proveedores**: Mismo cifrado Fernet en la tabla `config_dte`.
3. **JWT**: Access token de 15 min (en memoria del cliente), refresh token de 7 días (HttpOnly cookie).
4. **Rate limiting**: Redis-based, 10 req/s por IP en endpoints de auth, 100 req/s en POS.
5. **HTTPS obligatorio**: Certificado SSL en producción (Let's Encrypt o Cloudflare).
6. **Backup automático**: Dump de PostgreSQL diario, 30 días de retención.
7. **Soft delete**: Nada se elimina físicamente. Campo `deleted_at` + `deleted_by`.
8. **Impersonación SuperAdmin**: Token temporal de 30 min con log de todas las acciones.
9. **CORS**: Whitelist de dominios por tenant.
10. **Separación de ambientes MH**: Flag `ambiente` = `00` (pruebas) / `01` (producción) por tenant, nunca mezclar.

---

## 11. PLAN DE DESARROLLO SUGERIDO (Sprints)

| Sprint | Duración | Entregable |
|--------|----------|-----------|
| 1 | 2 sem | Auth multi-tenant + gestión usuarios + roles |
| 2 | 2 sem | Módulo productos + inventario + kardex básico |
| 3 | 2 sem | POS básico (FC sin DTE) + caja + impresión ticket |
| 4 | 2 sem | Integración DTE (CCF + FC) con ambiente pruebas MH |
| 5 | 2 sem | Clientes + CXC + reportes básicos |
| 6 | 2 sem | Compras + proveedores + CXP |
| 7 | 2 sem | Panel SuperAdmin + gestión tenants |
| 8 | 2 sem | Reportes avanzados + libro IVA + dashboard |
| 9 | 1 sem | Pruebas + correcciones + paso a producción MH |
| 10 | 1 sem | QA, documentación, deploy |

**Total estimado:** ~18 semanas para MVP completo

---

*Documento preparado para ser usado como contexto de implementación con IA generativa.*
*Stack: FastAPI + PostgreSQL + Python 3.12+*
