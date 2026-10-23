# Decisiones iniciales para FacturaPro 2.0 / BIOCORE

Estas son reglas de producto acordadas para implementar en PRs futuros. **No indican funcionalidades ya terminadas.**

## Plataforma de creadores

- Portal privado de propietarios y soporte técnico para dar de alta empresas.
- Activación de módulos opcionales por empresa, con límites y planes asignados.
- Deshabilitar módulos oculta y deniega su uso sin borrar los datos del cliente.
- Los permisos de módulo se comprueban en el backend además de la interfaz.
- El acceso extraordinario del personal de soporte a una empresa requiere autorización, duración limitada y auditoría.

## Usuarios y operación

- Cuenta de vendedor vinculada a sucursal y horarios específicos; bloqueos por vacaciones y asuetos.
- **Cumpleaños de vendedores:** listado interno visible únicamente por gerente y subgerente; no mostrar edades, felicitaciones, antigüedad ni cuentas regresivas en el dashboard.
- **Comisiones:** calculadas sobre el subtotal sin IVA y registradas en reportes internos.
- Precios de costo y venta con tratamiento de IVA explícito; guardar costos históricos por venta.
- Los estados de DTE deben reflejar la respuesta real de Hacienda; no marcar como aceptado un documento pendiente o rechazado.

## Identidad visual

- Mantener BIOCORE como identidad visual propuesta: verde `#00A37F`, oscuro `#13261F`, tipografía Archivo.
- Compartir componentes de interfaz entre portal de creadores y paneles de empresa.
- Aclarar denominación final entre plataforma BIOCORE y producto FacturaPro antes de publicar.

## Seguridad y datos

- No mezclar datos entre empresas; UUID validado antes de seleccionar schema por transacción.
- Conservación de secretos en variables de entorno, jamás en Git ni en respuestas API.
- Antes de migrar la versión PHP/MySQL, respaldar y validar integridad de la base de datos actual.
- DTE y certificados sujetos a validación de las especificaciones y el ambiente oficial vigente de El Salvador.

## Sprint 1 · Decisiones técnicas (autenticación, usuarios y roles)

Implementación guiada por `docs/PRD.md` y `docs/FLUJOS.md`. Donde se apartó del PRD, el motivo está aquí.

### Ajustes respecto al PRD

- **Estructura:** se mantiene `backend/app/` (el PRD §6 muestra `app/` en la raíz). Módulos con los nombres del PRD: `core/security.py`, `core/permissions.py`, `core/tenant.py`, `core/audit.py`, `models/platform.py`, `routers/auth.py`, `routers/platform.py`, `routers/empresa.py`, `services/tenant_service.py`, `services/email_service.py`.
- **Librerías:** PyJWT en lugar de `python-jose` y `bcrypt` directo en lugar de `passlib`. Ambas alternativas del PRD tienen mantenimiento irregular y `passlib` falla con versiones recientes de `bcrypt`. Mismo algoritmo (HS256, bcrypt).
- **Refresh token:** en la BD se guarda solo su hash SHA-256 (`sessions.refresh_token_hash`, no el token). Se rota en cada `/auth/refresh`; si alguien presenta un refresh ya usado, se revoca la sesión entera (posible robo).
- **Secreto TOTP:** se cifra con Fernet (`FERNET_KEY`) igual que los certificados y API keys del PRD §10, en lugar de guardarse en texto. Un mismo código no se acepta dos veces.
- **Columnas y tablas agregadas en `platform`:** `users.totp_habilitado`, `users.totp_ultimo_contador`, `users.debe_cambiar_password`, `users.updated_at`, `users.deleted_at/deleted_by` (soft delete del PRD §10.7); `sessions.ultimo_uso_at`, `sessions.revocada_at`, `sessions.motivo_revocacion`; `audit_log.user_agent` (PRD §3.2 pide user-agent por login); tabla `password_reset_tokens` para la recuperación de contraseña.
- **Restricciones en BD:** el rol debe ser uno del PRD §5, solo el SUPERADMIN existe sin empresa (y nunca dentro de una), correos en minúsculas.
- **NIT y NRC** se guardan solo con dígitos (como los pide el JSON del DTE): NIT de 14 dígitos o DUI de 9; NRC de 1 a 8 dígitos.

### Comportamiento

- **Rol y estado se leen de la BD en cada petición.** El access token solo identifica la sesión. Cambiar un rol, desactivar un usuario o suspender una empresa aplica en la siguiente petición, sin esperar los 15 minutos del token.
- **Bloqueo:** al 5.º intento fallido (contraseña o código 2FA) la cuenta se bloquea 30 minutos (configurable con `BLOQUEO_MINUTOS`) y se avisa por correo. Se desbloquea antes por el ADMIN (`/empresa/usuarios/{id}/desbloquear`) o restableciendo la contraseña por correo.
- **Contraseñas temporales:** el ADMIN inicial de cada empresa, los usuarios que crea el ADMIN y el SUPERADMIN de arranque reciben una contraseña temporal. Hasta cambiarla solo pueden usar `/auth/me`, `/auth/password/cambiar` y `/auth/logout`.
- **Política de contraseñas:** mínimo 10 caracteres, máximo 72 bytes (límite de bcrypt).
- **Aislamiento:** el schema de empresa se toma del `tenant_id` guardado en la BD, nunca del token, y se fija con `SET LOCAL` al inicio de cada transacción (listener `after_begin`), así no se pierde tras un `commit()` ni se filtra a otras peticiones por el pool de conexiones. Un usuario de otra empresa responde 404.
- **Alta de empresa atómica:** crear el registro, el schema, sus migraciones y el ADMIN ocurre en una sola transacción; si algo falla no queda nada a medias.
- **Migraciones:** `alembic.ini` tiene dos secciones. `platform` migra el schema global; `tenant` migra cada schema de empresa, que guarda su propia tabla `alembic_version`. `python -m app.cli migrar` aplica ambas y se ejecuta al arrancar el contenedor.
- **Suspender una empresa** no borra datos: bloquea el acceso y cierra todas sus sesiones.

### Ambigüedades del PRD resueltas provisionalmente (confirmar)

- **SUPERVISOR_CAJA** aparece en la jerarquía (§5) pero no en la matriz de permisos. Por ahora tiene exactamente los permisos de CAJERO.
- **AUDITOR** se define "solo lectura", pero la matriz le da ✅ en reportes y auditoría. Se limita a lectura en todos los módulos.
- **Anulación por CAJERO:** FLUJOS §7 y §12 permiten al cajero anular sin autorización durante los primeros 5 minutos, mientras la matriz le da ❌ en "Anular venta". Hay que definirlo antes del sprint de POS.
- **Alta de empresas en el Sprint 1:** el PRD la ubica en el Sprint 7, pero sin ella no se puede probar el login multiempresa. Se adelantó lo mínimo (crear, editar, suspender, activar). Límites por plan, módulos opcionales, impersonación y estadísticas quedan para el Sprint 7.
- **Correo único global** (PRD §4): una persona no puede pertenecer a dos empresas con el mismo correo.

### Pendiente para sprints siguientes

- Rate limiting por IP (PRD §10.4): requiere Redis, que aún no está en la infraestructura. El bloqueo por cuenta ya protege contra fuerza bruta a un usuario concreto.
- CORS por empresa (PRD §10.9): por ahora una lista global en `CORS_ORIGINS`.
- Asignar establecimiento y caja a cada usuario (FLUJOS §4): llega con el módulo de empresa (establecimientos y cajas).
- Impersonación del SUPERADMIN con token temporal de 30 minutos (PRD §10.8).
