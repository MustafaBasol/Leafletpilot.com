"""template models

Revision ID: 20260704_0003
Revises: 20260702_0002
Create Date: 2026-07-04 00:03:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260704_0003"
down_revision: str | None = "20260702_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("template_type", sa.String(length=64), nullable=False),
        sa.Column("is_global", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(is_global = true and market_id is null) or (is_global = false and market_id is not null)",
            name="ck_templates_market_scope",
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_templates_is_active", "templates", ["is_active"])
    op.create_index("ix_templates_is_global", "templates", ["is_global"])
    op.create_index("ix_templates_market_id", "templates", ["market_id"])
    op.create_index("ix_templates_slug", "templates", ["slug"])
    op.create_index(
        "uq_templates_global_slug",
        "templates",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("market_id IS NULL"),
    )
    op.create_index(
        "uq_templates_market_slug",
        "templates",
        ["market_id", "slug"],
        unique=True,
        postgresql_where=sa.text("market_id IS NOT NULL"),
    )
    op.create_foreign_key(
        "fk_campaigns_template_id_templates",
        "campaigns",
        "templates",
        ["template_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_campaigns_template_id_templates", "campaigns", type_="foreignkey")
    op.drop_index("uq_templates_market_slug", table_name="templates", postgresql_where=sa.text("market_id IS NOT NULL"))
    op.drop_index("uq_templates_global_slug", table_name="templates", postgresql_where=sa.text("market_id IS NULL"))
    op.drop_index("ix_templates_slug", table_name="templates")
    op.drop_index("ix_templates_market_id", table_name="templates")
    op.drop_index("ix_templates_is_global", table_name="templates")
    op.drop_index("ix_templates_is_active", table_name="templates")
    op.drop_table("templates")
