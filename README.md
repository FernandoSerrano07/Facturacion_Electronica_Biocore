# BIOCORE · Facturación Electrónica

Proyecto **FacturaPro 2.0**, SaaS multiempresa para El Salvador.

Tecnologías previstas: **Python 3.11+, FastAPI y PostgreSQL**.

**Estado:** fase inicial. No emite DTE ni comprobantes tributarios válidos ante Hacienda.

El desarrollo se organiza mediante `feature/*` → pull requests a `develop` → revisión → `main`.

Nunca subir archivos `.env`, claves API, contraseñas SMTP, certificados `.p12` ni datos privados de clientes.
