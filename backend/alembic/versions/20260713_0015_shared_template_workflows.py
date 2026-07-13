"""Add shared template ownership, visibility, and version metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260713_0015"
down_revision = "20260712_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("status", sa.String(32), server_default="draft", nullable=False))
    op.add_column("templates", sa.Column("visibility", sa.String(32), server_default="shared", nullable=False))
    op.add_column("templates", sa.Column("minimum_plan", sa.String(32), server_default="starter", nullable=False))
    op.add_column("templates", sa.Column("category", sa.String(120), nullable=True))
    op.add_column("templates", sa.Column("thumbnail_key", sa.String(1000), nullable=True))
    op.add_column("templates", sa.Column("source_template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("templates", sa.Column("source_version", sa.Integer(), nullable=True))
    op.add_column("templates", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("templates", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("templates", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_templates_source_template_id", "templates", "templates", ["source_template_id"], ["id"])
    op.create_index("ix_templates_status", "templates", ["status"])
    op.create_index("ix_templates_source_template_id", "templates", ["source_template_id"])
    op.execute("UPDATE templates SET status = CASE WHEN is_active THEN 'published' ELSE 'archived' END WHERE status = 'draft'")


def downgrade() -> None:
    op.drop_index("ix_templates_source_template_id", table_name="templates")
    op.drop_index("ix_templates_status", table_name="templates")
    op.drop_constraint("fk_templates_source_template_id", "templates", type_="foreignkey")
    for name in ("archived_at", "published_at", "version", "source_version", "source_template_id", "thumbnail_key", "category", "minimum_plan", "visibility", "status"):
        op.drop_column("templates", name)
