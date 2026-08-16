"""Add market_catalog_imports for the Phase 28D platform-admin catalog import.

Stores one row per Platform-Admin-initiated spreadsheet import job. The
uploaded workbook itself is never persisted; ``preview_payload``/
``result_payload`` hold the derived, JSON-safe row data needed to revalidate
and commit a previously generated preview.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260816_0024"
down_revision: str | None = "20260816_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_catalog_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_platform_admin_id", sa.Uuid(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("imported_rows", sa.Integer(), nullable=False),
        sa.Column("updated_rows", sa.Integer(), nullable=False),
        sa.Column("skipped_rows", sa.Integer(), nullable=False),
        sa.Column("failed_rows", sa.Integer(), nullable=False),
        sa.Column("preview_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_platform_admin_id"], ["platform_admins.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status in ('previewed', 'committed', 'expired', 'failed')",
            name="ck_market_catalog_imports_status",
        ),
    )
    op.create_index("ix_market_catalog_imports_market_id", "market_catalog_imports", ["market_id"])
    op.create_index("ix_market_catalog_imports_status", "market_catalog_imports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_market_catalog_imports_status", table_name="market_catalog_imports")
    op.drop_index("ix_market_catalog_imports_market_id", table_name="market_catalog_imports")
    op.drop_table("market_catalog_imports")
