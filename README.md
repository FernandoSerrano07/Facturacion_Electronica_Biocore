# BIOCORE · Facturación Electrónica

Base de **FacturaPro 2.0**, una plataforma SaaS multiempresa de facturación electrónica para El Salvador.

**Estado:** Sprint 1 del plan (`docs/PRD.md` §11) terminado: autenticación multiempresa, usuarios, roles RBAC y alta de empresas con schema propio. **Todavía no emite DTE ni facturas válidas ante Hacienda.**

## Documentación

- `docs/PRD.md`: requisitos del producto, modelo de datos, roles y plan por sprints.
- `docs/FLUJOS.md`: flujos por rol, venta, anulación, compras, kardex, caja y tokens de diseño.
- `docs/DECISIONES.md`: reglas de negocio acordadas y decisiones técnicas tomadas al implementar.

## Tecnologías

- Python 3.11+ y FastAPI
- PostgreSQL 16 con un schema por empresa (`tenant_<uuid>`) y el schema global `platform`
- SQLAlchemy 2 y Alembic (migraciones de `platform` y de cada empresa)
- JWT (PyJWT), bcrypt, TOTP (pyotp) y Fernet para secretos en reposo
- Docker Compose para servicios locales; Docker + Render para despliegue

## Iniciar el desarrollo

1. Copia `.env.example` a `.env` en la raíz y define una contraseña local fuerte para PostgreSQL.
2. Ejecuta `docker compose up -d` para iniciar PostgreSQL.
3. En `backend/`, crea un entorno virtual (`python -m venv .venv`), actívalo e instala dependencias: `pip install -r requirements.txt`.
4. Copia `backend/.env.example` a `backend/.env` y define al menos `DATABASE_URL`, `SECRET_KEY` y `FERNET_KEY` (el archivo indica cómo generarlas). Para crear el primer SUPERADMIN define también `SUPERADMIN_EMAIL` y `SUPERADMIN_PASSWORD`.
5. Desde `backend/`:
   - `python -m app.cli migrar` aplica las migraciones de `platform` y de todas las empresas.
   - `python -m app.cli crear-superadmin` crea el SUPERADMIN inicial (solo si todavía no existe ninguno).
   - `uvicorn app.main:app --reload` levanta la API.
6. Abre `http://127.0.0.1:8000/docs` para probar los endpoints. El SUPERADMIN entra con su contraseña inicial y debe cambiarla en `POST /auth/password/cambiar` antes de usar el resto.

Sin SMTP configurado, en desarrollo los correos (recuperación de contraseña, aviso de bloqueo) se escriben en el log de la API.

## Pruebas

Las pruebas de flujo usan un PostgreSQL real. Crea una base de datos desechable cuyo nombre contenga `test` (sus schemas se borran en cada corrida):

```bash
docker compose exec postgres createdb -U biocore biocore_test
cd backend
TEST_DATABASE_URL=postgresql+psycopg2://biocore:<tu-clave>@localhost:5432/biocore_test python -m pytest -q
```

Sin `TEST_DATABASE_URL` solo corren las pruebas unitarias. GitHub Actions (`.github/workflows/pruebas.yml`) ejecuta lint y todas las pruebas con PostgreSQL 16 en cada push y pull request.

## API del Sprint 1

| Ruta | Quién | Para qué |
|------|-------|----------|
| `POST /auth/login`, `POST /auth/login/2fa` | Todos | Login con correo y contraseña; si tiene 2FA, segundo paso con código TOTP |
| `POST /auth/refresh`, `POST /auth/logout` | Todos | Renovar el access token (refresh en cookie HttpOnly, rotativo) y cerrar sesión |
| `GET /auth/me` | Todos | Usuario, empresa, permisos por módulo y ruta inicial según el rol |
| `GET/DELETE /auth/sesiones`, `POST /auth/sesiones/cerrar-otras` | Todos | Ver y cerrar sesiones en otros dispositivos |
| `POST /auth/2fa/configurar`, `/activar`, `/desactivar` | Todos | Verificación en dos pasos opcional |
| `POST /auth/password/olvide`, `/restablecer`, `/cambiar` | Todos | Recuperación por correo (token de un uso, 1 hora) y cambio de contraseña |
| `/platform/tenants` (+ `/suspender`, `/activar`), `/platform/auditoria` | SUPERADMIN | Alta de empresas (crea schema, migra y crea su ADMIN), edición, suspensión y auditoría global |
| `/empresa/usuarios` (+ `/desbloquear`, `/restablecer-password`, `/desactivar-2fa`) | ADMIN_EMPRESA (GERENTE y AUDITOR solo lectura) | Usuarios de la empresa con roles del PRD |
| `GET /empresa/auditoria` | ADMIN_EMPRESA, AUDITOR | Log de acciones de la empresa |

## Despliegue en Render

`render.yaml` crea la base de datos y el servicio Docker. Al arrancar, el contenedor aplica las migraciones, crea el SUPERADMIN si se definió y levanta la API en el puerto que asigna Render. En el panel de Render define:

- `FERNET_KEY` (sin ella la verificación en dos pasos queda deshabilitada).
- `SUPERADMIN_EMAIL` y `SUPERADMIN_PASSWORD` para el primer ingreso.
- `FRONTEND_URL` y `CORS_ORIGINS` cuando exista el frontend; `SMTP_*` para enviar correos.

**Seguridad:** nunca subas archivos `.env`, contraseñas SMTP, certificados `.p12`, bases de datos con clientes reales ni claves de proveedores.

## Flujo de Git

- `main`: versión estable.
- `develop`: integración de funcionalidades aprobadas.
- `feature/*`: trabajo por módulo con *pull request* hacia `develop`.

## Próximos sprints (PRD §11)

2. Productos, inventario y kardex básico.
3. POS básico (FC sin DTE), caja e impresión de ticket.
4. Integración DTE (CCF + FC) con el ambiente de pruebas de Hacienda.
5. Clientes, cuentas por cobrar y reportes básicos.
6. Compras, proveedores y cuentas por pagar.
7. Panel SuperAdmin completo: planes con límites, módulos por empresa, impersonación auditada.
8. Reportes avanzados, libro de IVA y dashboard.
9. y 10. Pruebas, paso a producción ante Hacienda, QA y documentación.
