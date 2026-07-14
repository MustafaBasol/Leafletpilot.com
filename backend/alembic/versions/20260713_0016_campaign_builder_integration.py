"""Add version-safe campaign builder state and market product identity."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260713_0016"
down_revision = "20260713_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("snapshot_json", postgresql.JSONB(), nullable=True))
    op.add_column("campaigns", sa.Column("builder_config_json", postgresql.JSONB(), nullable=True))
    op.add_column("campaigns", sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("campaigns", sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("campaign_items", sa.Column("market_product_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_campaign_items_market_product_id", "campaign_items", "market_products", ["market_product_id"], ["id"])
    op.create_index("ix_campaign_items_market_product_id", "campaign_items", ["market_product_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_items_market_product_id", table_name="campaign_items")
    op.drop_constraint("fk_campaign_items_market_product_id", "campaign_items", type_="foreignkey")
    op.drop_column("campaign_items", "market_product_id")
    for name in ("finalized_at", "frozen_at", "builder_config_json", "snapshot_json"):
        op.drop_column("campaigns", name)
