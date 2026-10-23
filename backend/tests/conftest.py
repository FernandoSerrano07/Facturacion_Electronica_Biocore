"""Variables ficticias solo para pruebas sin conexiones a la base de datos."""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "unit-test-placeholder-not-for-production")
