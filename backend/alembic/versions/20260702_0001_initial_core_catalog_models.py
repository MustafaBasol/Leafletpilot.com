"""initial core catalog models

Revision ID: 20260702_0001
Revises:
Create Date: 2026-07-02 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260702_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "markets",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("logo_url", sa.String(length=1000), nullable=True),
        sa.Column("primary_color", sa.String(length=32), nullable=True),
        sa.Column("secondary_color", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_markets_slug", "markets", ["slug"], unique=True)

    op.create_table(
        "brands",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("logo_url", sa.String(length=1000), nullable=True),
        sa.Column("is_global", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(is_global = true and market_id is null) or "
            "(is_global = false and market_id is not null)",
            name="ck_brands_market_scope",
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brands_market_id", "brands", ["market_id"])
    op.create_index("ix_brands_slug", "brands", ["slug"])
    op.create_index(
        "uq_brands_global_slug",
        "brands",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("market_id IS NULL"),
    )
    op.create_index(
        "uq_brands_market_slug",
        "brands",
        ["market_id", "slug"],
        unique=True,
        postgresql_where=sa.text("market_id IS NOT NULL"),
    )

    op.create_table(
        "categories",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_global", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(is_global = true and market_id is null) or "
            "(is_global = false and market_id is not null)",
            name="ck_categories_market_scope",
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_categories_market_id", "categories", ["market_id"])
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_index("ix_categories_slug", "categories", ["slug"])
    op.create_index(
        "uq_categories_global_slug",
        "categories",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("market_id IS NULL"),
    )
    op.create_index(
        "uq_categories_market_slug",
        "categories",
        ["market_id", "slug"],
        unique=True,
        postgresql_where=sa.text("market_id IS NOT NULL"),
    )

    op.create_table(
        "market_users",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role in ('platform_admin', 'market_admin', 'market_staff', 'operator')",
            name="ck_market_users_role",
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "user_id", name="uq_market_users_market_id_user_id"),
    )
    op.create_index("ix_market_users_market_id", "market_users", ["market_id"])
    op.create_index("ix_market_users_user_id", "market_users", ["user_id"])

    op.create_table(
        "products",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_name", sa.String(length=120), nullable=True),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("package_size", sa.String(length=64), nullable=True),
        sa.Column("package_type", sa.String(length=64), nullable=True),
        sa.Column("is_global", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(is_global = true and market_id is null) or "
            "(is_global = false and market_id is not null)",
            name="ck_products_market_scope",
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_barcode", "products", ["barcode"])
    op.create_index("ix_products_brand_id", "products", ["brand_id"])
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_is_active", "products", ["is_active"])
    op.create_index("ix_products_is_global", "products", ["is_global"])
    op.create_index("ix_products_market_id", "products", ["market_id"])
    op.create_index("ix_products_name", "products", ["name"])

    op.create_table(
        "activity_logs",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_logs_created_at", "activity_logs", ["created_at"])
    op.create_index(
        "ix_activity_logs_entity_type_entity_id",
        "activity_logs",
        ["entity_type", "entity_id"],
    )
    op.create_index("ix_activity_logs_market_id", "activity_logs", ["market_id"])
    op.create_index("ix_activity_logs_user_id", "activity_logs", ["user_id"])

    op.create_table(
        "product_aliases",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "normalized_alias",
            name="uq_product_aliases_product_id_normalized_alias",
        ),
    )
    op.create_index(
        "ix_product_aliases_normalized_alias",
        "product_aliases",
        ["normalized_alias"],
    )

    op.create_table(
        "product_images",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=1000), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("image_type", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("has_transparent_background", sa.Boolean(), nullable=True),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quality_status in ('excellent', 'good', 'needs_review', 'missing')",
            name="ck_product_images_quality_status",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_images_is_primary", "product_images", ["is_primary"])
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_images_product_id", table_name="product_images")
    op.drop_index("ix_product_images_is_primary", table_name="product_images")
    op.drop_table("product_images")
    op.drop_index("ix_product_aliases_normalized_alias", table_name="product_aliases")
    op.drop_table("product_aliases")
    op.drop_index("ix_activity_logs_user_id", table_name="activity_logs")
    op.drop_index("ix_activity_logs_market_id", table_name="activity_logs")
    op.drop_index("ix_activity_logs_entity_type_entity_id", table_name="activity_logs")
    op.drop_index("ix_activity_logs_created_at", table_name="activity_logs")
    op.drop_table("activity_logs")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_index("ix_products_market_id", table_name="products")
    op.drop_index("ix_products_is_global", table_name="products")
    op.drop_index("ix_products_is_active", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_index("ix_products_brand_id", table_name="products")
    op.drop_index("ix_products_barcode", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_market_users_user_id", table_name="market_users")
    op.drop_index("ix_market_users_market_id", table_name="market_users")
    op.drop_table("market_users")
    op.drop_index("uq_categories_market_slug", table_name="categories")
    op.drop_index("uq_categories_global_slug", table_name="categories")
    op.drop_index("ix_categories_slug", table_name="categories")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_index("ix_categories_market_id", table_name="categories")
    op.drop_table("categories")
    op.drop_index("uq_brands_market_slug", table_name="brands")
    op.drop_index("uq_brands_global_slug", table_name="brands")
    op.drop_index("ix_brands_slug", table_name="brands")
    op.drop_index("ix_brands_market_id", table_name="brands")
    op.drop_table("brands")
    op.drop_index("ix_markets_slug", table_name="markets")
    op.drop_table("markets")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
