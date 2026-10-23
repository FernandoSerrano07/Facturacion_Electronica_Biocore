"""Schema platform inicial: tenants, usuarios, sesiones, recuperación y auditoría.

Revision ID: 0001
Revises:
Create Date: 2026-10-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("accion", sa.String(length=100), nullable=False),
        sa.Column("modulo", sa.String(length=50), nullable=False),
        sa.Column("entidad_id", sa.String(length=100), nullable=True),
        sa.Column("detalle", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
        schema="platform",
    )
    op.create_index(
        "ix_audit_log_tenant_id_created_at",
        "audit_log",
        ["tenant_id", "created_at"],
        unique=False,
        schema="platform",
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("razon_social", sa.String(length=200), nullable=False),
        sa.Column("nit", sa.String(length=20), nullable=True),
        sa.Column("nrc", sa.String(length=20), nullable=True),
        sa.Column("plan", sa.String(length=20), server_default="pro", nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("schema_name", sa.String(length=63), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("plan IN ('free', 'pro', 'enterprise')", name=op.f("ck_tenants_plan_valido")),
        sa.CheckConstraint(
            "schema_name ~ '^tenant_[0-9a-f]{32}$'", name=op.f("ck_tenants_schema_name_valido")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("nit", name=op.f("uq_tenants_nit")),
        sa.UniqueConstraint("schema_name", name=op.f("uq_tenants_schema_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
        schema="platform",
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=True),
        sa.Column("apellido", sa.String(length=100), nullable=True),
        sa.Column("rol", sa.String(length=30), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("totp_secret", sa.Text(), nullable=True),
        sa.Column("totp_habilitado", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("totp_ultimo_contador", sa.BigInteger(), nullable=True),
        sa.Column("debe_cambiar_password", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ultimo_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intentos_fallidos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(rol = 'SUPERADMIN') = (tenant_id IS NULL)",
            name=op.f("ck_users_superadmin_sin_tenant"),
        ),
        sa.CheckConstraint(
            "rol IN ('SUPERADMIN', 'ADMIN_EMPRESA', 'GERENTE', 'SUBGERENTE', 'SUPERVISOR_CAJA', 'CAJERO', 'VENDEDOR', 'CONTADOR', 'BODEGUERO', 'AUDITOR')",
            name=op.f("ck_users_rol_valido"),
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_minusculas")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["platform.tenants.id"],
            name=op.f("fk_users_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        schema="platform",
    )
    op.create_index(
        op.f("ix_platform_users_tenant_id"), "users", ["tenant_id"], unique=False, schema="platform"
    )
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["platform.users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
        schema="platform",
    )
    op.create_index(
        op.f("ix_platform_password_reset_tokens_user_id"),
        "password_reset_tokens",
        ["user_id"],
        unique=False,
        schema="platform",
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ultimo_uso_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_revocacion", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["platform.users.id"],
            name=op.f("fk_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        schema="platform",
    )
    op.create_index(
        op.f("ix_platform_sessions_user_id"),
        "sessions",
        ["user_id"],
        unique=False,
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_platform_sessions_user_id"), table_name="sessions", schema="platform")
    op.drop_table("sessions", schema="platform")
    op.drop_index(
        op.f("ix_platform_password_reset_tokens_user_id"),
        table_name="password_reset_tokens",
        schema="platform",
    )
    op.drop_table("password_reset_tokens", schema="platform")
    op.drop_index(op.f("ix_platform_users_tenant_id"), table_name="users", schema="platform")
    op.drop_table("users", schema="platform")
    op.drop_table("tenants", schema="platform")
    op.drop_index("ix_audit_log_tenant_id_created_at", table_name="audit_log", schema="platform")
    op.drop_table("audit_log", schema="platform")
