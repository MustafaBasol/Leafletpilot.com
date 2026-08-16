from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.market import Market


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (
        CheckConstraint(
            "(is_global = true and market_id is null) or (is_global = false and market_id is not null)",
            name="ck_brands_market_scope",
        ),
        Index("ix_brands_market_id", "market_id"),
        Index("ix_brands_slug", "slug"),
        Index("uq_brands_global_slug", "slug", unique=True, postgresql_where=text("market_id IS NULL")),
        Index(
            "uq_brands_market_slug",
            "market_id",
            "slug",
            unique=True,
            postgresql_where=text("market_id IS NOT NULL"),
        ),
    )

    market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(1000))
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    market: Mapped[Market | None] = relationship(back_populates="brands")
    products: Mapped[list[Product]] = relationship(back_populates="brand")
    aliases: Mapped[list[BrandAlias]] = relationship(back_populates="brand", cascade="all, delete-orphan")


class BrandAlias(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "brand_aliases"
    __table_args__ = (UniqueConstraint("brand_id", "normalized_alias", name="uq_brand_alias_brand_normalized"), Index("ix_brand_aliases_normalized_alias", "normalized_alias"))
    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[Brand] = relationship(back_populates="aliases")


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(
            "(is_global = true and market_id is null) or (is_global = false and market_id is not null)",
            name="ck_categories_market_scope",
        ),
        Index("ix_categories_market_id", "market_id"),
        Index("ix_categories_parent_id", "parent_id"),
        Index("ix_categories_slug", "slug"),
        Index(
            "uq_categories_global_slug",
            "slug",
            unique=True,
            postgresql_where=text("market_id IS NULL"),
        ),
        Index(
            "uq_categories_market_slug",
            "market_id",
            "slug",
            unique=True,
            postgresql_where=text("market_id IS NOT NULL"),
        ),
    )

    market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32))
    icon: Mapped[str | None] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    market: Mapped[Market | None] = relationship(back_populates="categories")
    parent: Mapped[Category | None] = relationship(remote_side="Category.id", back_populates="children")
    children: Mapped[list[Category]] = relationship(back_populates="parent")
    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "(is_global = true and market_id is null) or (is_global = false and market_id is not null)",
            name="ck_products_market_scope",
        ),
        Index("ix_products_market_id", "market_id"),
        Index("ix_products_brand_id", "brand_id"),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_barcode", "barcode"),
        Index("ix_products_name", "name"),
        Index("ix_products_is_active", "is_active"),
        Index("ix_products_is_global", "is_global"),
        Index("ix_products_merged_into_product_id", "merged_into_product_id"),
        CheckConstraint(
            "merged_into_product_id is null or merged_into_product_id <> id",
            name="ck_products_merged_not_self",
        ),
    )

    market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    brand_id: Mapped[UUID | None] = mapped_column(ForeignKey("brands.id"))
    category_id: Mapped[UUID | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(120))
    barcode: Mapped[str | None] = mapped_column(String(64))
    package_size: Mapped[str | None] = mapped_column(String(64))
    package_type: Mapped[str | None] = mapped_column(String(64))
    package_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    package_unit: Mapped[str | None] = mapped_column(String(16))
    package_type_canonical: Mapped[str | None] = mapped_column(String(64))
    regular_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    promo_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    badge_text: Mapped[str | None] = mapped_column(String(64))
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Merge sources stay as inactive redirects so historical references can
    # resolve predictably without a destructive product deletion.
    merged_into_product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("products.id", name="fk_products_merged_into_product_id")
    )
    quality_score: Mapped[int | None] = mapped_column(Integer)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    market: Mapped[Market | None] = relationship(back_populates="products")
    brand: Mapped[Brand | None] = relationship(back_populates="products")
    category: Mapped[Category | None] = relationship(back_populates="products")
    aliases: Mapped[list[ProductAlias]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
    merged_into: Mapped[Product | None] = relationship(
        remote_side="Product.id",
        foreign_keys=[merged_into_product_id],
        back_populates="merged_products",
    )
    merged_products: Mapped[list[Product]] = relationship(
        back_populates="merged_into",
        foreign_keys=[merged_into_product_id],
    )


class ProductAlias(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "product_aliases"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "normalized_alias",
            name="uq_product_aliases_product_id_normalized_alias",
        ),
        Index("ix_product_aliases_normalized_alias", "normalized_alias"),
    )

    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(64))

    product: Mapped[Product] = relationship(back_populates="aliases")


class ProductImage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "product_images"
    __table_args__ = (
        CheckConstraint(
            "quality_status in ('excellent', 'good', 'needs_review', 'missing', 'rejected')",
            name="ck_product_images_quality_status",
        ),
        Index("ix_product_images_product_id", "product_id"),
        Index("ix_product_images_is_primary", "is_primary"),
    )

    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    url: Mapped[str | None] = mapped_column(String(1000))
    image_type: Mapped[str] = mapped_column(String(32), default="main", nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    has_transparent_background: Mapped[bool | None] = mapped_column(Boolean)
    quality_status: Mapped[str] = mapped_column(String(32), default="needs_review", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product: Mapped[Product] = relationship(back_populates="images")


class CatalogQualityDecision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistent operator decisions for one canonical unordered product pair."""

    __tablename__ = "catalog_quality_decisions"
    __table_args__ = (
        CheckConstraint(
            "product_a_id <> product_b_id",
            name="ck_catalog_quality_decisions_distinct_products",
        ),
        CheckConstraint(
            "product_a_id < product_b_id",
            name="ck_catalog_quality_decisions_ordered_pair",
        ),
        CheckConstraint(
            "decision in ('ignored')",
            name="ck_catalog_quality_decisions_decision",
        ),
        UniqueConstraint(
            "product_a_id",
            "product_b_id",
            name="uq_catalog_quality_decisions_product_pair",
        ),
    )

    product_a_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", name="fk_catalog_quality_decisions_product_a"),
        nullable=False,
    )
    product_b_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", name="fk_catalog_quality_decisions_product_b"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(32), default="ignored", nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))
    created_by_platform_admin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "platform_admins.id",
            name="fk_catalog_quality_decisions_created_by_platform_admin",
        )
    )


class MarketProduct(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Market-owned presentation of a canonical or private product.

    Existing Product rows remain the compatibility identity used by campaigns,
    matching, aliases, and global images. This additive layer owns market
    pricing and presentation without mutating the canonical Product row.
    """

    __tablename__ = "market_products"
    __table_args__ = (
        CheckConstraint(
            "(product_id is not null) or (private_name is not null and length(trim(private_name)) > 0)",
            name="ck_market_products_identity",
        ),
        Index("ix_market_products_market_id", "market_id"),
        Index("ix_market_products_product_id", "product_id"),
        Index("ix_market_products_category_override_id", "category_override_id"),
        Index(
            "uq_market_products_market_product",
            "market_id",
            "product_id",
            unique=True,
            postgresql_where=text("product_id IS NOT NULL"),
        ),
        Index(
            "uq_market_products_legacy_product",
            "legacy_product_id",
            unique=True,
            postgresql_where=text("legacy_product_id IS NOT NULL"),
        ),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"))
    legacy_product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"))
    private_name: Mapped[str | None] = mapped_column(String(255))
    private_brand_text: Mapped[str | None] = mapped_column(String(255))
    private_barcode: Mapped[str | None] = mapped_column(String(64))
    private_sku: Mapped[str | None] = mapped_column(String(64))
    private_package_size: Mapped[str | None] = mapped_column(String(64))
    private_package_type: Mapped[str | None] = mapped_column(String(64))
    package_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    package_unit: Mapped[str | None] = mapped_column(String(16))
    package_type_canonical: Mapped[str | None] = mapped_column(String(64))
    display_name_override: Mapped[str | None] = mapped_column(String(255))
    category_override_id: Mapped[UUID | None] = mapped_column(ForeignKey("categories.id"))
    regular_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    promo_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    badge_text: Mapped[str | None] = mapped_column(String(64))
    stock_note: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_storage_key: Mapped[str | None] = mapped_column(String(1000))
    image_url: Mapped[str | None] = mapped_column(String(1000))
    image_mime_type: Mapped[str | None] = mapped_column(String(100))
    image_quality_status: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    market: Mapped[Market] = relationship()
    product: Mapped[Product | None] = relationship(foreign_keys=[product_id])
    legacy_product: Mapped[Product | None] = relationship(foreign_keys=[legacy_product_id])
    category_override: Mapped[Category | None] = relationship(foreign_keys=[category_override_id])
