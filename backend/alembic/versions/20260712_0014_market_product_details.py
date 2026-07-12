"""Add private market product fields."""

import sqlalchemy as sa
from alembic import op

revision = "20260712_0014"
down_revision = "20260712_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, length in (("private_brand_text", 255), ("private_barcode", 64), ("private_sku", 64), ("private_package_size", 64), ("private_package_type", 64)):
        op.add_column("market_products", sa.Column(name, sa.String(length), nullable=True))
    op.create_index("ix_market_products_private_barcode", "market_products", ["market_id", "private_barcode"])
    op.create_index("ix_market_products_private_sku", "market_products", ["market_id", "private_sku"])


def downgrade() -> None:
    op.drop_index("ix_market_products_private_sku", table_name="market_products")
    op.drop_index("ix_market_products_private_barcode", table_name="market_products")
    for name in ("private_package_type", "private_package_size", "private_sku", "private_barcode", "private_brand_text"):
        op.drop_column("market_products", name)
