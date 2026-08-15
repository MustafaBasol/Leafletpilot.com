"""Add normalized package fields and scoped brand aliases."""
import sqlalchemy as sa
from alembic import op

revision = "20260815_0021"
down_revision = "20260810_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("products", "market_products"):
        op.add_column(table, sa.Column("package_amount", sa.Numeric(12, 3), nullable=True))
        op.add_column(table, sa.Column("package_unit", sa.String(16), nullable=True))
        op.add_column(table, sa.Column("package_type_canonical", sa.String(64), nullable=True))
    op.create_table("brand_aliases",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("brand_id", sa.Uuid(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False), sa.Column("normalized_alias", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("brand_id", "normalized_alias", name="uq_brand_alias_brand_normalized"),
    )
    op.create_index("ix_brand_aliases_normalized_alias", "brand_aliases", ["normalized_alias"])


def downgrade() -> None:
    op.drop_index("ix_brand_aliases_normalized_alias", table_name="brand_aliases")
    op.drop_table("brand_aliases")
    for table in ("market_products", "products"):
        op.drop_column(table, "package_type_canonical"); op.drop_column(table, "package_unit"); op.drop_column(table, "package_amount")
