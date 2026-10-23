# FLUJOS Y ESQUEMAS — Sistema de Facturación Electrónica El Salvador
**Proyecto BIOCORE · Sistema SaaS Multi-tenant**  
**Stack:** Python (FastAPI) · PostgreSQL · DTE / MH El Salvador  

---

## 1. FLUJO GENERAL DEL SISTEMA (vista de 10,000 pies)

```
                    ┌─────────────────────────────────────┐
                    │         BIOCORE PLATAFORMA          │
                    │   (panel de superadmin / dueño)     │
                    └─────────────────┬───────────────────┘
                                      │ gestiona
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
    ┌─────────▼──────┐    ┌──────────▼─────┐    ┌──────────▼─────┐
    │  FARMACIA XYZ  │    │  TIENDA ABC    │    │ DISTRIBUIDORA  │
    │  (tenant_001)  │    │  (tenant_002)  │    │  (tenant_003)  │
    │                │    │                │    │                │
    │  Admin         │    │  Admin         │    │  Admin         │
    │  Gerente       │    │  Cajero        │    │  Contador      │
    │  Cajero x3     │    │  Bodeguero     │    │  Vendedor x5   │
    │  Bodeguero     │    │                │    │  Bodeguero     │
    └────────────────┘    └────────────────┘    └────────────────┘
              │                       │                       │
              └───────────────────────▼───────────────────────┘
                              ┌───────────────┐
                              │  MH EL SALVADOR│
                              │  API DTE       │
                              │  (vía Oyama,   │
                              │  Edicom, etc.) │
                              └───────────────┘
```

---

## 2. FLUJO DE AUTENTICACIÓN Y LOGIN

```
USUARIO ABRE EL SISTEMA
         │
         ▼
┌────────────────────┐
│ Pantalla de Login  │
│  email + password  │
└────────┬───────────┘
         │
         ▼
  ¿Credenciales válidas?
     /          \
   NO            SÍ
   │              │
   ▼              ▼
Incrementar   ¿Tiene 2FA activado?
intentos        /           \
fallidos       SÍ           NO
   │           │              │
   ▼           ▼              ▼
¿5 intentos? Pedir código  Generar JWT
    │        TOTP           access (15 min)
    │           │           + refresh (7 días)
    ▼           ▼              │
Bloquear    ¿Código OK?        ▼
cuenta →       /   \        Detectar tenant
notificar     NO    SÍ      del usuario
por email      │     │         │
               │     ▼         ▼
               ▼   Generar  ¿Tiene empresa activa?
            +1 intento JWT      /         \
                              NO           SÍ
                               │            │
                               ▼            ▼
                          Error:       Set search_path
                          empresa      = tenant_<id>
                          inactiva         │
                                           ▼
                                    Redirigir según ROL:
                                    ┌─────────────────────┐
                                    │ SUPERADMIN → /platform │
                                    │ ADMIN      → /empresa  │
                                    │ GERENTE    → /dashboard│
                                    │ CAJERO     → /pos      │
                                    │ CONTADOR   → /reportes │
                                    │ BODEGUERO  → /inventario│
                                    └─────────────────────┘
```

---

## 3. ESQUEMA POR ROL — SUPERADMIN (dueño de la plataforma)

**Accede a:** `/platform/*`

```
SUPERADMIN
    │
    ├── Dashboard de la Plataforma
    │     ├── Total de empresas activas
    │     ├── DTEs emitidos hoy (todas las empresas)
    │     └── Alertas: empresas con certificado próximo a vencer
    │
    ├── Gestión de Tenants (empresas)
    │     ├── Ver todas las empresas
    │     ├── Crear empresa nueva
    │     │     ├── Crear schema PostgreSQL: tenant_<id>
    │     │     ├── Ejecutar migraciones en ese schema
    │     │     └── Crear usuario ADMIN para esa empresa
    │     ├── Editar datos de empresa
    │     ├── Suspender / Activar empresa
    │     ├── Ver estadísticas de uso por empresa
    │     └── Impersonar usuario (token temporal 30 min)
    │           └── TODO queda registrado en audit_log
    │
    ├── Planes y Licencias
    │     ├── Asignar plan: Free / Pro / Enterprise
    │     └── Definir límites: usuarios, cajas, DTEs/mes
    │
    └── Actualizaciones del sistema
          ├── Deploy de nuevas versiones
          └── Migrar todos los schemas de una vez
```

---

## 4. ESQUEMA POR ROL — ADMIN EMPRESA

**Accede a:** Todo lo de su empresa. El primer usuario creado al dar de alta la empresa.

```
ADMIN EMPRESA
    │
    ├── Configuración de la Empresa
    │     ├── Datos fiscales: NIT, NRC, razón social, actividad
    │     ├── Establecimientos (sucursales): código MH, dirección
    │     ├── Cajas por establecimiento
    │     ├── Logo y datos de contacto (para DTEs y PDFs)
    │     └── Certificado digital .p12 (para firma DTE)
    │
    ├── Configuración DTE
    │     ├── Elegir proveedor: Oyama / Edicom / MH directo
    │     ├── API Key del proveedor (se cifra con Fernet)
    │     ├── Ambiente: Pruebas (00) o Producción (01)
    │     └── Numeración correlativa por tipo de DTE
    │
    ├── Gestión de Usuarios
    │     ├── Crear usuarios y asignar rol
    │     ├── Asignar establecimiento y caja
    │     ├── Restablecer contraseñas
    │     └── Activar / Desactivar usuarios
    │
    ├── Todos los módulos del sistema (acceso completo)
    └── Auditoría: ver log de acciones de todos los usuarios
```

---

## 5. ESQUEMA POR ROL — GERENTE

**Accede a:** Operación completa. No puede cambiar configuración fiscal ni DTE.

```
GERENTE
    │
    ├── Dashboard ejecutivo
    │     ├── Ventas del día / semana / mes
    │     ├── Productos más vendidos
    │     ├── Comparativo vs período anterior
    │     └── Alertas de stock bajo
    │
    ├── POS / Facturación (puede vender + ver todas las cajas)
    ├── Clientes (CRUD completo)
    ├── Productos e inventario (CRUD completo)
    ├── Compras y proveedores (CRUD completo)
    ├── Cuentas por cobrar (ver + registrar abonos)
    ├── Cuentas por pagar (ver + aprobar pagos)
    ├── Caja / Turnos (abrir, cerrar, ver arqueos de todas las cajas)
    ├── Anular ventas (con justificación → genera NC automática al MH)
    └── Reportes completos (ventas, inventario, libro IVA)
```

---

## 6. ESQUEMA POR ROL — SUBGERENTE

**Accede a:** Operación del día a día. Algunas acciones requieren autorización del Gerente.

```
SUBGERENTE
    │
    ├── POS / Facturación (vender)
    ├── Clientes (CRUD completo)
    ├── Productos (ver + editar. NO puede eliminar)
    ├── Inventario
    │     ├── Ver kardex y existencias
    │     └── Solicitar ajuste de inventario (requiere aprobación Gerente)
    ├── Compras
    │     ├── Crear orden de compra
    │     └── Registrar recepción de mercadería
    ├── Cuentas por cobrar (ver + registrar abonos)
    ├── Cuentas por pagar (SOLO VER — pagos los aprueba Gerente)
    ├── Caja / Arqueo (solo su caja asignada)
    └── Reportes básicos (ventas del día, su caja)
```

---

## 7. ESQUEMA POR ROL — CAJERO

**Accede a:** Únicamente el POS y su caja. El rol más restringido del día a día.

```
CAJERO
    │
    ├── Apertura de caja
    │     └── Ingresar monto inicial en efectivo
    │
    ├── POS — Punto de Venta
    │     ├── Buscar producto (código de barras / nombre)
    │     ├── Agregar al carrito
    │     ├── Aplicar descuento (si tiene permiso habilitado)
    │     ├── Seleccionar tipo DTE: FC (consumidor) o CCF (empresa)
    │     │     └── Si CCF: buscar cliente por NIT o ingresar datos
    │     ├── Seleccionar forma de pago
    │     │     ├── Efectivo → calcular cambio
    │     │     ├── Tarjeta → ingresar referencia
    │     │     └── Transferencia → ingresar referencia
    │     ├── Generar venta → DTE emitido al MH automáticamente
    │     ├── Imprimir ticket / PDF
    │     └── SOLO puede anular si tiene < 5 minutos (luego necesita Gerente)
    │
    ├── Ver su historial de ventas del turno
    │
    └── Cierre de caja
          ├── Contar efectivo en caja
          ├── Ver resumen del turno
          └── Generar arqueo (lo ve el Gerente/Admin)
```

---

## 8. ESQUEMA POR ROL — VENDEDOR

**Accede a:** Cotizaciones y ventas, sin manejo de caja ni inventario.

```
VENDEDOR
    │
    ├── POS (facturar, sin apertura/cierre de caja propia)
    ├── Clientes
    │     ├── Ver y crear clientes
    │     └── Ver historial de compras de su cartera
    ├── Productos (solo ver precios y existencias)
    ├── Cuentas por cobrar
    │     └── Ver saldo de sus clientes
    └── Reportes
          └── Sus propias ventas del período
```

---

## 9. ESQUEMA POR ROL — CONTADOR

**Accede a:** Información fiscal y financiera. Sin acceso a ventas directas.

```
CONTADOR
    │
    ├── Libro de ventas IVA (formato MH)
    ├── Libro de compras IVA (formato MH)
    ├── Historial de DTEs emitidos (FC, CCF, NC, ND)
    ├── Cuentas por cobrar (ver estado completo)
    ├── Cuentas por pagar (ver + registrar pagos)
    ├── Reportes financieros
    │     ├── Ventas por período con desglose de IVA
    │     ├── Compras por período
    │     ├── Cuentas aging (vencidas, por vencer)
    │     └── Inventario valorado (existencias × costo)
    └── Configuración de empresa
          └── Solo lectura (ver datos fiscales)
```

---

## 10. ESQUEMA POR ROL — BODEGUERO

**Accede a:** Inventario y compras. Sin acceso a ventas ni reportes financieros.

```
BODEGUERO
    │
    ├── Productos
    │     ├── Ver catálogo completo con existencias
    │     └── Editar descripción y foto (NO puede cambiar precio)
    │
    ├── Inventario
    │     ├── Ver kardex por producto y por bodega
    │     ├── Ver stock actual
    │     ├── Solicitar ajuste de inventario (requiere aprobación)
    │     └── Registrar traslado entre bodegas
    │
    ├── Compras
    │     ├── Ver órdenes de compra pendientes
    │     └── Registrar recepción de mercadería
    │           ├── Verificar cantidades contra OC
    │           ├── Registrar número de lote / vencimiento (farmacias)
    │           └── Actualizar kardex automáticamente
    │
    └── Alertas de stock mínimo
```

---

## 11. FLUJO COMPLETO DE UNA VENTA (POS → Inventario → DTE → MH)

```
CAJERO / VENDEDOR en el POS
         │
         ▼
1. BÚSQUEDA DE PRODUCTO
   ├── Escanear código de barras → producto encontrado
   ├── Buscar por nombre → lista de coincidencias
   └── Agregar al carrito con cantidad
                │
                ▼
2. VALIDACIÓN DE STOCK
   ├── Sistema consulta tabla `inventario` (cantidad actual en bodega)
   ├── ¿Hay suficiente stock?
   │     SÍ → continúa
   │     NO → alerta visual "Stock insuficiente"
   └── (opcional) Forzar venta sin stock si Admin lo permite
                │
                ▼
3. DATOS DEL CLIENTE
   ├── FC (Consumidor Final):
   │     └── No requiere datos fiscales (nombre opcional)
   └── CCF (Crédito Fiscal):
         └── Buscar por NIT o ingresar:
               ├── NIT / NRC
               ├── Razón social
               └── Dirección
                │
                ▼
4. FORMA DE PAGO
   ├── Efectivo → ingresar monto recibido → calcular cambio
   ├── Tarjeta → ingresar referencia de autorización
   ├── Mixto  → efectivo + tarjeta
   └── Crédito → días de plazo (genera CXC automáticamente)
                │
                ▼
5. CONFIRMAR VENTA
   │
   ├── Sistema asigna número de control correlativo
   │     └── DTE-03-C001-000000000000001 (CCF)
   │         DTE-01-C001-000000000000001 (FC)
   │
   ├── INSERT en tabla `ventas` (estado: 'borrador')
   ├── INSERT en tabla `venta_items`
   └── INSERT en tabla `venta_pagos`
                │
                ▼
6. DESCUENTO DE INVENTARIO (automático)
   ├── Por cada item vendido:
   │     ├── UPDATE `inventario` SET cantidad = cantidad - qty
   │     │     (en la bodega asignada a la caja)
   │     ├── INSERT en `kardex`:
   │     │     tipo = 'VENTA'
   │     │     cantidad = -qty (negativo)
   │     │     saldo_cantidad = stock anterior - qty
   │     └── Si farmacia: descontar del lote PEPS (más antiguo primero)
   └── Actualizar costo promedio si aplica
                │
                ▼
7. EMISIÓN DTE (asíncrono, no bloquea al cajero)
   │
   ├── DTEService construye JSON según esquema MH:
   │     ├── identificacion (tipo, número control, UUID, fecha, hora)
   │     ├── emisor (datos fiscales del tenant)
   │     ├── receptor (datos del cliente)
   │     ├── cuerpoDocumento (items, precios, tributos)
   │     └── resumen (subtotales, IVA, total)
   │
   ├── Firmar JSON con certificado digital .p12
   │
   ├── POST a API del proveedor DTE (Oyama / Edicom / MH directo)
   │
   ├── Respuesta del MH:
   │     ├── ACEPTADO → guardar sello de recepción + UUID
   │     │     UPDATE `ventas` SET estado = 'aceptado'
   │     ├── RECHAZADO → guardar observaciones
   │     │     UPDATE `ventas` SET estado = 'rechazado'
   │     │     (alerta al Admin para revisar y reenviar)
   │     └── ERROR DE RED → reintentar en 30s (Celery task)
   │
   └── Generar PDF de representación gráfica
         ├── Con logo de la empresa
         ├── Datos fiscales + QR con código de verificación MH
         └── Guardar en S3 / Cloudinary
                │
                ▼
8. ENTREGA AL CLIENTE
   ├── Imprimir ticket 80mm (impresora térmica)
   ├── Imprimir PDF carta (si CCF o cliente lo pide)
   └── Enviar PDF por email (opcional)
```

---

## 12. FLUJO DE ANULACIÓN DE VENTA / NOTA DE CRÉDITO

```
SOLICITUD DE ANULACIÓN
         │
         ▼
¿Quién solicita?
    │
    ├── CAJERO (< 5 min después de emitida)
    │     └── Puede anular sin autorización
    │
    └── CAJERO (> 5 min) / VENDEDOR
          └── Solicita al GERENTE / ADMIN
                    │
                    ▼
              ¿Aprueba?
                /   \
              NO     SÍ
              │       │
              ▼       ▼
           Rechazar  Generar Nota de Crédito (NC)
                      │
                      ├── Tipo DTE: "05" (Nota de Crédito)
                      ├── Referencia a la venta original
                      ├── Emitir al MH (misma lógica DTE)
                      ├── Revertir kardex:
                      │     INSERT kardex tipo = 'DEVOLUCION_VENTA'
                      │     UPDATE inventario SET cantidad = cantidad + qty
                      └── UPDATE ventas SET estado = 'anulado'
```

---

## 13. FLUJO DE COMPRA → ENTRADA AL INVENTARIO (Kardex)

```
CREACIÓN DE ORDEN DE COMPRA
    ├── Seleccionar proveedor
    ├── Agregar productos con cantidades y precios
    └── Estado inicial: 'pendiente'
         │
         ▼
APROBACIÓN (Gerente / Admin)
    └── Estado: 'aprobada' → enviar al proveedor
         │
         ▼
RECEPCIÓN DE MERCADERÍA (Bodeguero)
    ├── Seleccionar OC a recibir
    ├── Ingresar cantidades reales recibidas
    │     (puede ser parcial → estado: 'recibida_parcial')
    ├── Si farmacia: ingresar número de lote y fecha de vencimiento
    │     └── INSERT en tabla `lotes`
    └── Al confirmar recepción:
          ├── UPDATE inventario SET cantidad = cantidad + qty_recibida
          ├── Recalcular costo promedio:
          │     nuevo_costo_prom = (stock_actual × costo_actual + qty_nueva × precio_compra) / nuevo_stock
          ├── INSERT en kardex:
          │     tipo = 'COMPRA'
          │     cantidad = +qty (positivo)
          │     costo_unitario = precio_compra
          │     saldo_cantidad = stock anterior + qty
          └── Actualizar estado OC: 'recibida' / 'recibida_parcial'
```

---

## 14. FLUJO DE KARDEX (cómo se conecta todo)

```
TABLA KARDEX — registro cronológico de TODOS los movimientos

Cada movimiento tiene:
  ├── producto_id  → qué producto se movió
  ├── bodega_id    → en qué bodega
  ├── tipo_movimiento:
  │     COMPRA             → +entrada
  │     VENTA              → -salida
  │     DEVOLUCION_VENTA   → +entrada (revertir venta)
  │     DEVOLUCION_COMPRA  → -salida (devolver a proveedor)
  │     AJUSTE_POS         → +entrada (ajuste físico positivo)
  │     AJUSTE_NEG         → -salida (ajuste físico negativo)
  │     TRASLADO_SALIDA    → -salida (de bodega origen)
  │     TRASLADO_ENTRADA   → +entrada (en bodega destino)
  ├── documento_tipo → venta | compra | ajuste | traslado
  ├── documento_id   → ID del documento origen
  ├── cantidad       → positivo=entrada / negativo=salida
  ├── costo_unitario → precio unitario al momento del movimiento
  ├── saldo_cantidad → stock acumulado DESPUÉS del movimiento
  └── user_id        → quién ejecutó la acción

El saldo_cantidad en el último registro = stock actual
(igual al campo `cantidad` en tabla `inventario`)
```

---

## 15. FLUJO DE CIERRE DE CAJA

```
CAJERO al finalizar su turno
         │
         ▼
1. Solicitar cierre de caja en el sistema
         │
         ▼
2. Sistema muestra resumen del turno:
   ├── Total ventas efectivo
   ├── Total ventas tarjeta
   ├── Total ventas transferencia
   ├── Egresos (pagos de caja chica)
   └── Saldo esperado en caja
         │
         ▼
3. Cajero cuenta el efectivo físico
   └── Ingresa monto contado
         │
         ▼
4. Sistema calcula diferencia:
   diferencia = monto_contado - saldo_esperado
         │
         ▼
5. Guardar arqueo:
   ├── diferencia = 0     → "Cuadrado"
   ├── diferencia > 0     → "Sobrante" (alerta al Gerente)
   └── diferencia < 0     → "Faltante" (alerta al Gerente)
         │
         ▼
6. Caja cerrada → no puede seguir facturando
   └── El dinero queda "pendiente de retiro" para el Gerente
```

---

## 16. ESQUEMA DE TABLAS CLAVE Y SUS RELACIONES

```
tenants (platform)
    └─── users (platform)
              │
              ├── (dentro del schema del tenant):
              │
              ▼
         establecimientos
              │
              ├── cajas
              │     └── turnos_caja
              │               └── ventas
              │                     ├── venta_items ──► productos
              │                     └── venta_pagos       │
              │                                           │
              └── bodegas                                 │
                    ├── inventario ◄────────────────────┘
                    └── kardex

         clientes
              └── ventas (FK cliente_id)
              └── cuentas_cobrar
                    └── cuentas_cobrar_abonos

         productos
              ├── categorias
              ├── unidades_medida
              ├── inventario (por bodega)
              ├── lotes (para farmacias)
              └── kardex

         proveedores
              └── ordenes_compra
                    └── ordenes_compra_items ──► productos

         config_dte (API del proveedor, certificado cifrado)
              └── usado por ventas para emitir DTEs
```

---

## 17. TOKENS DE DISEÑO BIOCORE PARA EL FRONTEND

El sistema debe construirse sobre la identidad visual de BIOCORE:

### Paleta de colores
```
Principal (marca):
  brand          #00A37F   → botones primarios, acentos, hexágono del logo
  brand-bright   #1FCB9C   → sobre fondos oscuros
  brand-strong   #007A5F   → texto verde sobre fondo claro

Fondos:
  surface        #E9EFEC   → fondo de página (modo claro)
  surface-raised #FFFFFF   → tarjetas y modales
  night          #0F172A   → fondo modo oscuro / headers oscuros
  ink-deep       #13261F   → fondo oscuro de marca (navbar, footers)

Texto:
  ink            #13261F   → texto principal
  ink-muted      #4A5D55   → texto secundario, labels
  on-brand       #13261F   → texto SOBRE botones verdes
  white          #FFFFFF   → texto sobre night e ink-deep

Bordes:
  line           #C9D6D0   → divisores y bordes decorativos
```

### Tipografía
```
Familia única: Archivo (Google Fonts)

Titulares:
  display   56px / bold 800   → portadas, banners
  h1        40px / bold 800   → título de página
  h2        28px / bold 700   → secciones
  h3        20px / bold 700   → títulos de tarjetas

Texto:
  body      16px / regular 400  → párrafos, descripciones
  small     14px / regular 400  → notas, fechas, labels
  label     12px / bold 700 / uppercase / spacing 0.12em → etiquetas
```

### Espaciado y bordes
```
Espaciado:
  space-1:  4px    space-4: 16px
  space-2:  8px    space-6: 24px
  space-8: 32px    space-12: 48px

Bordes redondeados:
  radius-sm:   6px   → inputs, chips
  radius-md:  12px   → botones, tarjetas
  radius-lg:  24px   → cards grandes, imágenes
  radius-pill: 999px → badges, pills
```

### Reglas de diseño para el sistema
1. **Navbar / sidebar:** fondo `ink-deep` (#13261F), texto `white`, acento activo en `brand`
2. **Botón primario:** fondo `brand` (#00A37F), texto `on-brand` (#13261F). Nunca texto blanco sobre `brand`
3. **Botón secundario:** borde `brand`, texto `brand-strong`, fondo transparente
4. **Botón destructivo (eliminar):** rojo #DC2626 (excepcional, no es color de marca)
5. **Cards de dashboard:** fondo `surface-raised` (#FFFFFF), borde `line`, sombra suave
6. **Tablas:** cabecera fondo `ink-deep`, texto blanco; filas alternas con `surface`
7. **Alertas de éxito:** verde `brand` con fondo suave
8. **Alertas de error:** rojo, no usar verde para errores
9. **Logo:** usar variante clara sobre fondos claros, oscura sobre `night`/`ink-deep`
10. **No introducir** otros colores (morados, naranjas, degradados arcoíris)

---

*Documento preparado para ser usado como contexto de implementación con IA generativa.*  
*Marca: BIOCORE · Stack: FastAPI + PostgreSQL + Python 3.12+*
