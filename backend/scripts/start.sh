#!/bin/sh
# Arranque del contenedor: migraciones, SUPERADMIN inicial (si se definió) y API.
set -e

python -m app.cli migrar
python -m app.cli crear-superadmin

# --proxy-headers toma la IP real del cliente desde X-Forwarded-For solo si el proxy
# está en FORWARDED_ALLOW_IPS (uvicorn lee esa variable; por defecto 127.0.0.1).
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
