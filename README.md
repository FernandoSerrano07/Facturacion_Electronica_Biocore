# BIOCORE · Facturación Electrónica

Base inicial de **FacturaPro 2.0**, una plataforma SaaS multiempresa para El Salvador.

**Estado:** proyecto en construcción. Esta primera entrega contiene únicamente la API de salud, configuración, utilidades de aislamiento por empresa, entorno local y pruebas. **No emite DTE ni facturas válidas ante Hacienda.**

## Tecnologías

- Python 3.11+ y FastAPI
- PostgreSQL 16, SQLAlchemy y Alembic (migraciones por implementar)
- Docker Compose para servicios locales

## Iniciar el desarrollo

1. Copia `.env.example` a `.env` en la raíz y define una contraseña local fuerte para PostgreSQL.
2. Ejecuta `docker compose up -d` para iniciar PostgreSQL.
3. En `backend/`, crea un entorno virtual: `python -m venv .venv` y actívalo.
4. Instala dependencias: `pip install -r requirements.txt`.
5. Copia `backend/.env.example` a `backend/.env` y configura `DATABASE_URL` y `SECRET_KEY` para el entorno local.
6. Desde `backend/`, ejecuta `uvicorn app.main:app --reload`.
7. Abre `http://127.0.0.1:8000/health` para comprobar la API.
8. Ejecuta las pruebas desde `backend/`: `python -m pytest -q`.

**Seguridad:** nunca subas archivos `.env`, contraseñas SMTP, certificados `.p12`, bases de datos con clientes reales ni claves de proveedores.

## Flujo de Git

- `main`: versión estable.
- `develop`: integración de funcionalidades aprobadas.
- `feature/*`: trabajo por módulo con *pull request* hacia `develop`.

## Próximos módulos

1. Plataforma: registro y suspensión de empresas, planes y habilitación de módulos.
2. Autenticación y permisos RBAC con aislamiento multiempresa probado.
3. Empresa, personal, clientes y catálogo de productos.
4. POS, inventario, Kardex, comisiones y correos.
5. DTE: implementar y validar requisitos oficiales vigentes del Ministerio de Hacienda antes de pruebas y producción.

Consulta `docs/DECISIONES.md` para reglas de negocio acordadas.
