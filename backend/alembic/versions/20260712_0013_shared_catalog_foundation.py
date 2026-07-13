"""Add market product associations for the shared catalog foundation."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260712_0013"
down_revision: str | None = "20260711_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("markets", sa.Column("subscription_plan", sa.String(length=32), nullable=True))
    op.create_table(
        "market_products",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("legacy_product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("private_name", sa.String(length=255), nullable=True),
        sa.Column("display_name_override", sa.String(length=255), nullable=True),
        sa.Column("category_override_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("regular_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("promo_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        sa.Column("badge_text", sa.String(length=64), nullable=True),
        sa.Column("stock_note", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("image_storage_key", sa.String(length=1000), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("image_mime_type", sa.String(length=100), nullable=True),
        sa.Column("image_quality_status", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(product_id is not null) or (private_name is not null and length(trim(private_name)) > 0)",
            name="ck_market_products_identity",
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["legacy_product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["category_override_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_products_market_id", "market_products", ["market_id"])
    op.create_index("ix_market_products_product_id", "market_products", ["product_id"])
    op.create_index("ix_market_products_category_override_id", "market_products", ["category_override_id"])
    op.create_index(
        "uq_market_products_market_product",
        "market_products",
        ["market_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("product_id IS NOT NULL"),
    )
    op.create_index(
        "uq_market_products_legacy_product",
        "market_products",
        ["legacy_product_id"],
        unique=True,
        postgresql_where=sa.text("legacy_product_id IS NOT NULL"),
    )

    connection = op.get_bind()
    legacy_rows = connection.execute(
        sa.text(
            """
            SELECT id, market_id, name, category_id, regular_price, promo_price,
                   currency, badge_text, sort_order, is_active
            FROM products
            WHERE is_global = false AND market_id IS NOT NULL
            """
        )
    ).mappings()
    for row in legacy_rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO market_products (
                    id, market_id, legacy_product_id, private_name, category_override_id,
                    regular_price, promo_price, currency, badge_text, sort_order,
                    is_active, created_at, updated_at
                )
                SELECT
                    :id, :market_id, :legacy_product_id, :private_name, :category_override_id,
                    :regular_price, :promo_price, :currency, :badge_text, :sort_order,
                    :is_active, NOW(), NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM market_products WHERE legacy_product_id = :legacy_product_id
                )
                """
            ),
            {
                "id": uuid4(),
                "market_id": row["market_id"],
                "legacy_product_id": row["id"],
                "private_name": row["name"],
                "category_override_id": row["category_id"],
                "regular_price": row["regular_price"],
                "promo_price": row["promo_price"],
                "currency": row["currency"],
                "badge_text": row["badge_text"],
                "sort_order": row["sort_order"],
                "is_active": row["is_active"],
            },
        )


def downgrade() -> None:
    op.drop_index("uq_market_products_legacy_product", table_name="market_products")
    op.drop_index("uq_market_products_market_product", table_name="market_products")
    op.drop_index("ix_market_products_category_override_id", table_name="market_products")
    op.drop_index("ix_market_products_product_id", table_name="market_products")
    op.drop_index("ix_market_products_market_id", table_name="market_products")
    op.drop_table("market_products")
    op.drop_column("markets", "subscription_plan")
