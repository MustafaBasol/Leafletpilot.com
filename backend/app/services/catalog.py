import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ActivityLog,
    Brand,
    BrandAlias,
    Category,
    Market,
    MarketProduct,
    Product,
    ProductAlias,
    ProductImage,
)
from app.schemas.brand import BrandCreate, BrandUpdate
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.schemas.market_product import MarketProductUpdate
from app.schemas.product import ProductAliasCreate, ProductCreate, ProductUpdate
from app.services.catalog_matching import (
    CatalogMatchResult,
    canonical_name_key,
    canonical_package_key,
    eligible_global_product_conditions,
    match_global_products,
)
from app.services.entitlements import has_capacity, require_capability, resolve_capabilities
from app.services.image_pipeline import store_flyer_image
from app.services.product_identity import normalize_barcode, normalize_product_text, normalize_words
from app.services.product_normalization import (
    format_package,
    normalize_package_type,
    normalized_package_values,
)

PUNCTUATION_RE = re.compile(r"[!\"#$%&'()*+,./:;<=>?@\[\\\]^_`{|}~-]+")
SPACES_RE = re.compile(r"\s+")
_MARKET_IDENTITY_FIELDS = frozenset(
    {
        "display_name_override",
        "private_brand_text",
        "private_barcode",
        "private_sku",
        "private_package_size",
        "private_package_type",
        "package_amount",
        "package_unit",
        "package_type_canonical",
    }
)


def slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = PUNCTUATION_RE.sub(" ", slug)
    slug = SPACES_RE.sub("-", slug).strip("-")
    return slug or "item"


def normalize_alias(value: str) -> str:
    return normalize_product_text(value)


@dataclass(frozen=True)
class ReconciledAlias:
    """The deterministic display value for one normalized alias identity."""

    alias: str
    normalized_alias: str


def reconcile_aliases(values: Iterable[str]) -> list[ReconciledAlias]:
    """Collapse blank and equivalent aliases while preserving first display text."""
    reconciled: list[ReconciledAlias] = []
    seen: set[str] = set()
    for value in values:
        alias = value.strip()
        normalized_alias = normalize_alias(alias)
        if not normalized_alias or normalized_alias in seen:
            continue
        seen.add(normalized_alias)
        reconciled.append(ReconciledAlias(alias=alias, normalized_alias=normalized_alias))
    return reconciled


def resolve_market_scope(is_global: bool, market_id: UUID | None) -> UUID | None:
    if is_global:
        return None
    if market_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Market-Id is required for market-specific catalog records.",
        )
    return market_id


def apply_scope_filters(
    statement: Select[tuple[Any]],
    model: type[Brand] | type[Category] | type[Product],
    market_id: UUID | None,
    include_global: bool,
) -> Select[tuple[Any]]:
    if market_id is None:
        return statement.where(model.is_global.is_(True))

    if include_global:
        return statement.where(
            or_(
                model.market_id == market_id,
                model.is_global.is_(True),
            )
        )
    return statement.where(model.market_id == market_id)


async def list_brands(
    session: AsyncSession,
    *,
    market_id: UUID | None,
    include_global: bool,
    search: str | None,
    is_active: bool | None,
    is_global: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[Brand], int]:
    statement = apply_scope_filters(select(Brand), Brand, market_id, include_global)
    if search:
        normalized = normalize_alias(search)
        statement = statement.where(or_(Brand.name.ilike(f"%{search}%"), Brand.aliases.any(BrandAlias.normalized_alias.ilike(f"%{normalized}%"))))
    if is_active is not None:
        statement = statement.where(Brand.is_active.is_(is_active))
    if is_global is not None:
        statement = statement.where(Brand.is_global.is_(is_global))

    return await _list(session, statement.order_by(Brand.name), limit, offset)


async def _brands_for_normalized_name(session: AsyncSession, normalized: str, market_id: UUID | None) -> list[Brand]:
    statement = select(Brand).options(selectinload(Brand.aliases)).where(or_(Brand.aliases.any(BrandAlias.normalized_alias == normalized), Brand.name.ilike(normalized)))
    statement = statement.where(Brand.is_global.is_(True)) if market_id is None else statement.where(Brand.market_id == market_id)
    return [brand for brand in (await session.scalars(statement)).unique().all() if normalize_alias(brand.name) == normalized or any(alias.normalized_alias == normalized for alias in brand.aliases)]


async def create_brand(session: AsyncSession, payload: BrandCreate, market_id: UUID | None) -> Brand:
    if payload.is_global: raise _global_mutation_forbidden()
    data = payload.model_dump(); data["name"] = data["name"].strip(); normalized = normalize_alias(data["name"])
    global_matches = await _brands_for_normalized_name(session, normalized, None)
    if len(global_matches) == 1: return global_matches[0]
    if len(global_matches) > 1: raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Brand alias is ambiguous in the global catalog.")
    scoped_market_id = resolve_market_scope(False, market_id); local_matches = await _brands_for_normalized_name(session, normalized, scoped_market_id)
    if len(local_matches) == 1: return local_matches[0]
    if len(local_matches) > 1: raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Brand alias is ambiguous in this market.")
    data["slug"] = data["slug"] or slugify(data["name"]); data["market_id"] = scoped_market_id
    brand = Brand(**data); brand.aliases = [BrandAlias(alias=data["name"], normalized_alias=normalized)]
    return await _persist(session, brand)


async def get_brand(session: AsyncSession, brand_id: UUID, market_id: UUID | None) -> Brand:
    brand = await _get_scoped(session, Brand, brand_id, market_id)
    if brand is None:
        raise _not_found("Brand")
    return brand


async def update_brand(
    session: AsyncSession,
    brand_id: UUID,
    payload: BrandUpdate,
    market_id: UUID | None,
) -> Brand:
    brand = await get_brand(session, brand_id, market_id)
    if brand.is_global:
        raise _global_mutation_forbidden()
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, key, value)
    return await _persist(session, brand)


async def delete_brand(session: AsyncSession, brand_id: UUID, market_id: UUID | None) -> Brand:
    brand = await get_brand(session, brand_id, market_id)
    if brand.is_global:
        raise _global_mutation_forbidden()
    brand.is_active = False
    return await _persist(session, brand)


async def list_categories(
    session: AsyncSession,
    *,
    market_id: UUID | None,
    include_global: bool,
    search: str | None,
    parent_id: UUID | None,
    is_active: bool | None,
    is_global: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[Category], int]:
    statement = apply_scope_filters(select(Category), Category, market_id, include_global)
    if search:
        statement = statement.where(Category.name.ilike(f"%{search}%"))
    if parent_id is not None:
        statement = statement.where(Category.parent_id == parent_id)
    if is_active is not None:
        statement = statement.where(Category.is_active.is_(is_active))
    if is_global is not None:
        statement = statement.where(Category.is_global.is_(is_global))

    return await _list(session, statement.order_by(Category.sort_order, Category.name), limit, offset)


async def create_category(
    session: AsyncSession,
    payload: CategoryCreate,
    market_id: UUID | None,
) -> Category:
    if payload.is_global:
        raise _global_mutation_forbidden()
    data = payload.model_dump()
    data["slug"] = data["slug"] or slugify(data["name"])
    data["market_id"] = resolve_market_scope(data["is_global"], market_id)
    category = Category(**data)
    return await _persist(session, category)


async def get_category(session: AsyncSession, category_id: UUID, market_id: UUID | None) -> Category:
    category = await _get_scoped(session, Category, category_id, market_id)
    if category is None:
        raise _not_found("Category")
    return category


async def update_category(
    session: AsyncSession,
    category_id: UUID,
    payload: CategoryUpdate,
    market_id: UUID | None,
) -> Category:
    category = await get_category(session, category_id, market_id)
    if category.is_global:
        raise _global_mutation_forbidden()
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, key, value)
    return await _persist(session, category)


async def delete_category(session: AsyncSession, category_id: UUID, market_id: UUID | None) -> Category:
    category = await get_category(session, category_id, market_id)
    if category.is_global:
        raise _global_mutation_forbidden()
    category.is_active = False
    return await _persist(session, category)


async def list_products(
    session: AsyncSession,
    *,
    market_id: UUID | None,
    include_global: bool,
    search: str | None,
    brand_id: UUID | None,
    category_id: UUID | None,
    barcode: str | None,
    is_active: bool | None,
    is_global: bool | None,
    has_image: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[Product], int]:
    statement = apply_scope_filters(
        select(Product).options(selectinload(Product.aliases), selectinload(Product.images)),
        Product,
        market_id,
        include_global,
    )
    if search:
        statement = statement.where(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.short_name.ilike(f"%{search}%"),
                Product.barcode.ilike(f"%{search}%"),
            )
        )
    if brand_id is not None:
        statement = statement.where(Product.brand_id == brand_id)
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if barcode:
        statement = statement.where(Product.barcode == barcode)
    if is_active is not None:
        statement = statement.where(Product.is_active.is_(is_active))
    if is_global is not None:
        statement = statement.where(Product.is_global.is_(is_global))
    if has_image is not None:
        statement = statement.where(Product.images.any() if has_image else ~Product.images.any())

    return await _list(session, statement.order_by(Product.sort_order, Product.name), limit, offset)


async def create_product(
    session: AsyncSession,
    payload: ProductCreate,
    market_id: UUID | None,
) -> Product:
    if payload.is_global:
        raise _global_mutation_forbidden()
    scoped_market_id = resolve_market_scope(False, market_id)
    await _lock_market(session, scoped_market_id)
    brand = await _validate_scoped_reference(
        session, Brand, payload.brand_id, scoped_market_id, "Brand"
    )
    await _validate_scoped_reference(
        session, Category, payload.category_id, scoped_market_id, "Category"
    )
    await _ensure_no_local_duplicate(
        session,
        market_id=scoped_market_id,
        name=payload.name,
        brand=brand.name if brand else None,
        barcode=payload.barcode,
        package_size=payload.package_size,
        package_amount=payload.package_amount,
        package_unit=payload.package_unit,
        package_type=payload.package_type_canonical or payload.package_type,
    )
    match = await match_global_products(
        session,
        market_id=scoped_market_id,
        name=payload.name,
        barcode=payload.barcode,
        brand_id=payload.brand_id,
        package_size=payload.package_size,
        package_type=payload.package_type,
        package_amount=payload.package_amount,
        package_unit=payload.package_unit,
        package_type_canonical=payload.package_type_canonical,
    )
    _enforce_global_match_decision(match, allow_override=payload.allow_global_match_override)
    data = normalized_package_values(
        payload.model_dump(
            exclude={"aliases", "images", "allow_global_match_override"},
            exclude_unset=True,
        )
    )
    _validate_structured_package_pair(data)
    data["market_id"] = scoped_market_id
    product = Product(id=uuid4(), **data)
    product.aliases = _build_aliases(payload.aliases)
    product.images = [ProductImage(**image.model_dump()) for image in payload.images]
    if match.match_type != "none":
        _add_catalog_activity(
            session,
            market_id=scoped_market_id,
            entity_type="product",
            entity_id=product.id,
            action="local_product_created_despite_global_match",
            metadata={"match_type": match.match_type, "legacy_endpoint": True},
        )
    return await _persist(session, product)


async def get_product(session: AsyncSession, product_id: UUID, market_id: UUID | None) -> Product:
    statement = (
        select(Product)
        .options(
            selectinload(Product.aliases),
            selectinload(Product.images),
            selectinload(Product.brand).selectinload(Brand.aliases),
            selectinload(Product.category),
        )
        .where(Product.id == product_id)
        .execution_options(populate_existing=True)
    )
    statement = apply_scope_filters(statement, Product, market_id, include_global=True)
    product = await session.scalar(statement)
    if product is None:
        raise _not_found("Product")
    return product


async def update_product(
    session: AsyncSession,
    product_id: UUID,
    payload: ProductUpdate,
    market_id: UUID | None,
) -> Product:
    product = await get_product(session, product_id, market_id)
    if product.is_global:
        raise _global_mutation_forbidden()
    if market_id is not None:
        await _lock_market(session, market_id)
        # The pre-lock read supports the established global-mutation guard. The
        # post-lock populated read is authoritative for concurrent local PATCHes.
        product = await get_product(session, product_id, market_id)
    data = normalized_package_values(payload.model_dump(exclude_unset=True))
    _validate_structured_package_pair(data)
    brand_id = data.get("brand_id", product.brand_id)
    brand = product.brand
    if "brand_id" in data:
        brand = await _validate_scoped_reference(
            session, Brand, brand_id, product.market_id, "Brand"
        )
    if "category_id" in data:
        await _validate_scoped_reference(
            session, Category, data["category_id"], product.market_id, "Category"
        )
    await _ensure_no_local_duplicate(
        session,
        market_id=product.market_id,
        name=data.get("name", product.name),
        brand=brand.name if brand else None,
        barcode=data.get("barcode", product.barcode),
        package_size=data.get("package_size", product.package_size),
        package_amount=data.get("package_amount", product.package_amount),
        package_unit=data.get("package_unit", product.package_unit),
        package_type=data.get(
            "package_type_canonical",
            data.get("package_type", product.package_type_canonical or product.package_type),
        ),
        exclude_product_id=product.id,
    )
    for key, value in data.items():
        setattr(product, key, value)
    return await _persist(session, product)


async def delete_product(session: AsyncSession, product_id: UUID, market_id: UUID | None) -> Product:
    product = await get_product(session, product_id, market_id)
    if product.is_global:
        raise _global_mutation_forbidden()
    product.is_active = False
    return await _persist(session, product)


async def create_product_alias(
    session: AsyncSession,
    product_id: UUID,
    payload: ProductAliasCreate,
    market_id: UUID | None,
) -> ProductAlias:
    product = await get_product(session, product_id, market_id)
    if product.is_global:
        raise _global_mutation_forbidden()
    normalized_alias = normalize_alias(payload.alias)
    duplicate = await session.scalar(
        select(ProductAlias)
        .join(Product, Product.id == ProductAlias.product_id)
        .where(
            Product.market_id == product.market_id,
            ProductAlias.normalized_alias == normalized_alias,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A catalog alias with this normalized identity already exists in this market.",
        )
    alias = _build_alias(payload)
    product.aliases.append(alias)
    await _persist(session, product)
    return alias


async def delete_product_alias(
    session: AsyncSession,
    product_id: UUID,
    alias_id: UUID,
    market_id: UUID | None,
) -> None:
    product = await get_product(session, product_id, market_id)
    if product.is_global:
        raise _global_mutation_forbidden()
    alias = next((item for item in product.aliases if item.id == alias_id), None)
    if alias is None:
        raise _not_found("Product alias")
    await session.delete(alias)
    await session.commit()


async def _list(
    session: AsyncSession,
    statement: Select[tuple[Any]],
    limit: int,
    offset: int,
) -> tuple[list[Any], int]:
    total_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = await session.scalar(total_statement)
    result = await session.scalars(statement.limit(limit).offset(offset))
    return list(result.unique().all()), total or 0


async def _get_scoped(
    session: AsyncSession,
    model: type[Brand] | type[Category],
    item_id: UUID,
    market_id: UUID | None,
) -> Brand | Category | None:
    statement = select(model).where(model.id == item_id)
    statement = apply_scope_filters(statement, model, market_id, include_global=True)
    return await session.scalar(statement)


async def _persist(session: AsyncSession, instance: Any) -> Any:
    session.add(instance)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Catalog record conflicts with existing data.",
        ) from exc
    return instance


def _build_alias(alias: str | ProductAliasCreate) -> ProductAlias:
    if isinstance(alias, str):
        value = alias
        source = None
    else:
        value = alias.alias
        source = alias.source
    return ProductAlias(alias=value, normalized_alias=normalize_alias(value), source=source)


def _build_aliases(aliases: Iterable[str | ProductAliasCreate]) -> list[ProductAlias]:
    source_by_normalized_alias: dict[str, str | None] = {}
    values: list[str] = []
    for alias in aliases:
        if isinstance(alias, str):
            value, source = alias, None
        else:
            value, source = alias.alias, alias.source
        normalized_alias = normalize_alias(value)
        source_by_normalized_alias.setdefault(normalized_alias, source)
        values.append(value)
    return [
        ProductAlias(
            alias=alias.alias,
            normalized_alias=alias.normalized_alias,
            source=source_by_normalized_alias[alias.normalized_alias],
        )
        for alias in reconcile_aliases(values)
    ]


def _not_found(label: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found.")


@dataclass(frozen=True)
class EffectiveProduct:
    name: str
    image_storage_key: str | None
    image_url: str | None
    category_id: UUID | None


def resolve_effective_product(
    product: Product | None, market_product: MarketProduct | None
) -> EffectiveProduct:
    global_image = next(
        (
            image
            for image in (product.images if product is not None else [])
            if image.is_primary and image.quality_status in {"excellent", "good"}
        ),
        None,
    )
    return EffectiveProduct(
        name=(
            market_product.display_name_override
            if market_product and market_product.display_name_override
            else None
        )
        or (product.name if product is not None else None)
        or (market_product.private_name if market_product else None)
        or "Unnamed product",
        image_storage_key=(market_product.image_storage_key if market_product else None)
        or (global_image.storage_key if global_image else None),
        image_url=(market_product.image_url if market_product else None)
        or (global_image.url if global_image else None),
        category_id=(market_product.category_override_id if market_product else None)
        or (product.category_id if product is not None else None),
    )


async def search_global_products(
    session: AsyncSession,
    *,
    search: str | None,
    barcode: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Product], int]:
    statement = (
        select(Product)
        .options(
            selectinload(Product.aliases),
            selectinload(Product.images),
            selectinload(Product.brand),
            selectinload(Product.category),
        )
        .where(*eligible_global_product_conditions())
    )
    if search:
        normalized = normalize_alias(search)
        statement = statement.where(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.short_name.ilike(f"%{search}%"),
                Product.barcode.ilike(f"%{search}%"),
                Product.aliases.any(ProductAlias.normalized_alias.ilike(f"%{normalized}%")),
                Product.brand.has(Brand.name.ilike(f"%{search}%")),
                Product.category.has(Category.name.ilike(f"%{search}%")),
            )
        )
    if barcode:
        statement = statement.where(Product.barcode == barcode)
    return await _list(session, statement.order_by(Product.name), limit, offset)


async def adopt_global_product(
    session: AsyncSession,
    *,
    market_id: UUID,
    product_id: UUID,
    regular_price: Any = None,
    promo_price: Any = None,
    currency: str = "EUR",
    **values: Any,
) -> MarketProduct:
    market = await _lock_market(session, market_id)
    product = await session.scalar(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.aliases),
            selectinload(Product.brand).selectinload(Brand.aliases),
            selectinload(Product.category),
        )
        .where(Product.id == product_id, *eligible_global_product_conditions())
    )
    if product is None:
        raise _not_found("Global product")
    require_capability(market, "global_catalog_access")
    await _validate_scoped_reference(
        session,
        Category,
        values.get("category_override_id"),
        market_id,
        "Category",
    )
    existing = await session.scalar(
        select(MarketProduct).where(
            MarketProduct.market_id == market_id, MarketProduct.product_id == product_id
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Global product is already adopted by this market.",
        )
    values = _normalized_market_product_values(values)
    _validate_structured_package_pair(values)
    effective_identity = _effective_global_identity(product, values)
    await _ensure_no_local_duplicate(
        session,
        market_id=market_id,
        **effective_identity,
        canonical_product=product,
    )
    association = MarketProduct(
        id=uuid4(),
        market_id=market_id,
        product_id=product_id,
        regular_price=regular_price,
        promo_price=promo_price,
        currency=currency,
        **{key: value for key, value in values.items() if value is not None},
    )
    session.add(association)
    _add_catalog_activity(
        session,
        market_id=market_id,
        entity_type="market_product",
        entity_id=association.id,
        action="global_product_adopted",
        metadata={"global_product_id": str(product_id)},
    )
    return await _persist(session, association)


async def create_private_market_product(
    session: AsyncSession,
    *,
    market_id: UUID,
    private_name: str,
    regular_price: Any = None,
    promo_price: Any = None,
    currency: str = "EUR",
    allow_global_match_override: bool = False,
    **values: Any,
) -> MarketProduct:
    market = await _lock_market(session, market_id)
    capabilities = resolve_capabilities(market)
    current_count = await session.scalar(
        select(func.count(MarketProduct.id)).where(
            MarketProduct.market_id == market_id, MarketProduct.product_id.is_(None)
        )
    )
    if not has_capacity(current_count or 0, capabilities.private_products_limit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Private product limit reached for this plan.",
        )
    await _validate_scoped_reference(
        session,
        Category,
        values.get("category_override_id"),
        market_id,
        "Category",
    )
    values = _normalized_market_product_values(values)
    _validate_structured_package_pair(values)
    effective_name = values.get("display_name_override") or private_name
    await _ensure_no_local_duplicate(
        session,
        market_id=market_id,
        name=effective_name,
        brand=values.get("private_brand_text"),
        barcode=values.get("private_barcode"),
        sku=values.get("private_sku"),
        package_size=values.get("private_package_size"),
        package_amount=values.get("package_amount"),
        package_unit=values.get("package_unit"),
        package_type=values.get("package_type_canonical") or values.get("private_package_type"),
    )
    match = await match_global_products(
        session,
        market_id=market_id,
        name=effective_name,
        barcode=values.get("private_barcode"),
        brand=values.get("private_brand_text"),
        package_size=values.get("private_package_size"),
        package_type=values.get("private_package_type"),
        package_amount=values.get("package_amount"),
        package_unit=values.get("package_unit"),
        package_type_canonical=values.get("package_type_canonical"),
    )
    _enforce_global_match_decision(match, allow_override=allow_global_match_override)
    association = MarketProduct(
        id=uuid4(),
        market_id=market_id,
        private_name=private_name,
        regular_price=regular_price,
        promo_price=promo_price,
        currency=currency,
        **{key: value for key, value in values.items() if value is not None},
    )
    session.add(association)
    if match.match_type != "none":
        _add_catalog_activity(
            session,
            market_id=market_id,
            entity_type="market_product",
            entity_id=association.id,
            action="local_product_created_despite_global_match",
            metadata={
                "match_type": match.match_type,
                "candidate_ids": [str(candidate.product.id) for candidate in match.candidates],
            },
        )
    return await _persist(session, association)


async def list_my_market_products(session: AsyncSession, market_id: UUID) -> list[MarketProduct]:
    result = await session.scalars(
        select(MarketProduct)
        .options(
            selectinload(MarketProduct.product).selectinload(Product.brand),
            selectinload(MarketProduct.product).selectinload(Product.category),
            selectinload(MarketProduct.product).selectinload(Product.images),
            selectinload(MarketProduct.legacy_product),
            selectinload(MarketProduct.category_override),
        )
        .where(MarketProduct.market_id == market_id)
        .order_by(MarketProduct.sort_order, MarketProduct.created_at)
    )
    return [
        row
        for row in result.unique().all()
        if row.product_id is None or _is_shared_product(row.product)
    ]


async def get_market_product(
    session: AsyncSession, market_product_id: UUID, market_id: UUID
) -> MarketProduct:
    row = await session.scalar(
        select(MarketProduct)
        .options(
            selectinload(MarketProduct.product).selectinload(Product.brand),
            selectinload(MarketProduct.product).selectinload(Product.aliases),
            selectinload(MarketProduct.product)
            .selectinload(Product.brand)
            .selectinload(Brand.aliases),
            selectinload(MarketProduct.product).selectinload(Product.category),
            selectinload(MarketProduct.product).selectinload(Product.images),
            selectinload(MarketProduct.legacy_product),
            selectinload(MarketProduct.category_override),
        )
        .where(MarketProduct.id == market_product_id, MarketProduct.market_id == market_id)
        .execution_options(populate_existing=True)
    )
    if row is None or (row.product_id is not None and not _is_shared_product(row.product)):
        raise _not_found("Market product")
    return row


async def update_market_product(
    session: AsyncSession, market_product_id: UUID, market_id: UUID, payload: MarketProductUpdate
) -> MarketProduct:
    await _lock_market(session, market_id)
    row = await get_market_product(session, market_product_id, market_id)
    data = _normalized_market_product_values(payload.model_dump(exclude_unset=True))
    await _validate_scoped_reference(
        session,
        Category,
        data.get("category_override_id"),
        market_id,
        "Category",
    )
    if data.get("private_package_size", object()) is None:
        data.setdefault("package_amount", None)
        data.setdefault("package_unit", None)
    if data.get("private_package_type", object()) is None:
        data.setdefault("package_type_canonical", None)
    _validate_structured_package_pair(data)
    merged = {
        "private_name": row.private_name,
        "display_name_override": row.display_name_override,
        "private_brand_text": row.private_brand_text,
        "private_barcode": row.private_barcode,
        "private_sku": row.private_sku,
        "private_package_size": row.private_package_size,
        "private_package_type": row.private_package_type,
        "package_amount": row.package_amount,
        "package_unit": row.package_unit,
        "package_type_canonical": row.package_type_canonical,
        **data,
    }
    if row.product_id is None:
        if not merged.get("private_name"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A local product name is required.",
            )
        await _ensure_no_local_duplicate(
            session,
            market_id=market_id,
            name=merged.get("display_name_override") or merged["private_name"],
            brand=merged.get("private_brand_text"),
            barcode=merged.get("private_barcode"),
            sku=merged.get("private_sku"),
            package_size=merged.get("private_package_size"),
            package_amount=merged.get("package_amount"),
            package_unit=merged.get("package_unit"),
            package_type=merged.get("package_type_canonical") or merged.get("private_package_type"),
            exclude_market_product_id=row.id,
            exclude_product_id=row.legacy_product_id,
        )
    elif _MARKET_IDENTITY_FIELDS.intersection(data):
        effective_identity = _effective_global_identity(row.product, merged)
        await _ensure_no_local_duplicate(
            session,
            market_id=market_id,
            **effective_identity,
            exclude_market_product_id=row.id,
            exclude_product_id=row.legacy_product_id,
            canonical_product=row.product,
        )
    for key, value in data.items():
        setattr(row, key, value)
    return await _persist(session, row)


async def link_local_market_product(
    session: AsyncSession,
    *,
    market_product_id: UUID,
    market_id: UUID,
    product_id: UUID,
) -> MarketProduct:
    market = await _lock_market(session, market_id)
    require_capability(market, "global_catalog_access")
    row = await session.scalar(
        select(MarketProduct)
        .options(
            selectinload(MarketProduct.product).selectinload(Product.brand),
            selectinload(MarketProduct.product).selectinload(Product.category),
            selectinload(MarketProduct.legacy_product).selectinload(Product.brand),
            selectinload(MarketProduct.category_override),
        )
        .where(
            MarketProduct.id == market_product_id,
            MarketProduct.market_id == market_id,
        )
        .with_for_update()
    )
    if row is None or (row.product_id is not None and not _is_shared_product(row.product)):
        raise _not_found("Market product")
    if row.legacy_product_id is not None and not _is_local_legacy_product(
        row.legacy_product,
        market_id,
    ):
        raise _not_found("Market product")
    if row.product_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Market product is already linked to the global catalog.",
        )
    if not _is_visible_category(row.category_override, market_id):
        raise _not_found("Category")
    target = await session.scalar(
        select(Product)
        .options(
            selectinload(Product.aliases),
            selectinload(Product.brand).selectinload(Brand.aliases),
            selectinload(Product.category),
        )
        .where(Product.id == product_id, *eligible_global_product_conditions())
    )
    if target is None:
        raise _not_found("Global product")
    existing = await session.scalar(
        select(MarketProduct.id).where(
            MarketProduct.market_id == market_id,
            MarketProduct.product_id == product_id,
            MarketProduct.id != row.id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Global product is already adopted by this market.",
        )
    link_values = {
        "display_name_override": row.display_name_override or row.private_name,
        "private_brand_text": row.private_brand_text,
        "private_barcode": row.private_barcode,
        "private_sku": row.private_sku,
        "private_package_size": row.private_package_size,
        "private_package_type": row.private_package_type,
        "package_amount": row.package_amount,
        "package_unit": row.package_unit,
        "package_type_canonical": row.package_type_canonical,
    }
    await _ensure_no_local_duplicate(
        session,
        market_id=market_id,
        **_effective_global_identity(target, link_values),
        exclude_market_product_id=row.id,
        exclude_product_id=row.legacy_product_id,
        canonical_product=target,
    )
    if row.private_name and not row.display_name_override:
        row.display_name_override = row.private_name
    row.product_id = product_id
    _add_catalog_activity(
        session,
        market_id=market_id,
        entity_type="market_product",
        entity_id=row.id,
        action="local_product_linked_to_global",
        metadata={
            "global_product_id": str(product_id),
            "legacy_product_id": str(row.legacy_product_id) if row.legacy_product_id else None,
        },
    )
    await _persist(session, row)
    return await get_market_product(session, row.id, market_id)


def resolved_market_product(row: MarketProduct) -> dict[str, Any]:
    product = row.product
    if product is not None and not _is_shared_product(product):
        product = None
    public_product_id = (
        product.id
        if product is not None
        else (
            row.legacy_product_id
            if row.product_id is None
            and row.legacy_product_id is not None
            and _is_local_legacy_product(row.legacy_product, row.market_id)
            else None
        )
    )
    effective = resolve_effective_product(product, row)
    global_brand = product.brand.name if product and product.brand else None
    global_category = product.category.name if product and product.category else None
    category_override = (
        row.category_override
        if _is_visible_category(row.category_override, row.market_id)
        else None
    )
    market_image_url = (
        row.image_url
        if row.image_url and urlparse(row.image_url).scheme in {"http", "https"}
        else None
    )
    image_url = (
        effective.image_url
        if effective.image_url and urlparse(effective.image_url).scheme in {"http", "https"}
        else None
    )
    if effective.image_storage_key:
        image_url = (
            f"/api/catalog/my-products/{row.id}/image/content"
            if row.image_storage_key
            else f"/api/catalog/shared/{row.product_id}/image/content"
        )
    inherited_image_url = None
    if product is not None:
        inherited = resolve_effective_product(product, None)
        if inherited.image_storage_key:
            inherited_image_url = f"/api/catalog/shared/{product.id}/image/content"
        elif inherited.image_url and urlparse(inherited.image_url).scheme in {"http", "https"}:
            inherited_image_url = inherited.image_url
    has_override = bool(
        row.private_name
        or row.display_name_override
        or row.category_override_id
        or row.badge_text
        or row.stock_note
        or row.image_storage_key
        or market_image_url
        or row.regular_price is not None
        or row.promo_price is not None
        or row.private_brand_text
        or row.private_barcode
        or row.private_sku
        or row.private_package_size
        or row.private_package_type
        or row.package_amount is not None
        or row.package_unit is not None
        or row.package_type_canonical is not None
        or row.sort_order
        or not row.is_active
        or (product is not None and row.currency != (product.currency or "EUR"))
    )
    source_state = "local" if product is None else ("global_override" if has_override else "global")
    inherited_values = {
        "name": product.name if product else None,
        "brand": global_brand if product else None,
        "package_size": product.package_size if product else None,
        "package_type": product.package_type if product else None,
        "package_amount": product.package_amount if product else None,
        "package_unit": product.package_unit if product else None,
        "package_type_canonical": product.package_type_canonical if product else None,
        "regular_price": product.regular_price if product else None,
        "promo_price": product.promo_price if product else None,
        "currency": product.currency if product else None,
        "badge_text": product.badge_text if product else None,
        "image_url": inherited_image_url,
    }
    override_values = {
        "private_name": row.private_name,
        "display_name_override": row.display_name_override,
        "private_brand_text": row.private_brand_text,
        "private_barcode": row.private_barcode,
        "private_sku": row.private_sku,
        "private_package_size": row.private_package_size,
        "private_package_type": row.private_package_type,
        "package_amount": row.package_amount,
        "package_unit": row.package_unit,
        "package_type_canonical": row.package_type_canonical,
        "regular_price": row.regular_price,
        "promo_price": row.promo_price,
        "currency": row.currency,
        "badge_text": row.badge_text,
        "stock_note": row.stock_note,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
        "image_url": (
            f"/api/catalog/my-products/{row.id}/image/content"
            if row.image_storage_key
            else market_image_url
        ),
    }
    has_market_package_override = row.package_amount is not None and row.package_unit is not None
    return {
        "id": row.id,
        "market_id": row.market_id,
        "product_id": public_product_id,
        "global_product_id": product.id if product is not None else None,
        "name": effective.name,
        "brand": row.private_brand_text or global_brand,
        "category": category_override.name if category_override else global_category,
        "package_size": row.private_package_size
        or format_package(row.package_amount, row.package_unit)
        or (product.package_size if product else None),
        "package_type": row.private_package_type or (product.package_type if product else None),
        "package_amount": row.package_amount
        if has_market_package_override
        else (product.package_amount if product else None),
        "package_unit": row.package_unit
        if has_market_package_override
        else (product.package_unit if product else None),
        "package_type_canonical": row.package_type_canonical
        if row.package_type_canonical is not None
        else (product.package_type_canonical if product else None),
        "regular_price": row.regular_price
        if row.regular_price is not None
        else (product.regular_price if product else None),
        "promo_price": row.promo_price
        if row.promo_price is not None
        else (product.promo_price if product else None),
        "currency": row.currency or (product.currency if product else "EUR"),
        "badge_text": row.badge_text or (product.badge_text if product else None),
        "stock_note": row.stock_note,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
        "source_type": ("Global with tenant override" if has_override else "Global")
        if product is not None
        else "Private",
        "source_state": source_state,
        "inherited_values": inherited_values,
        "override_values": override_values,
        "image_url": image_url,
        "image_override_active": bool(row.image_storage_key or market_image_url),
        "promo_active": row.promo_price is not None,
    }


async def upload_market_product_image(session: AsyncSession, market_product_id: UUID, market_id: UUID, content: bytes, mime_type: str) -> MarketProduct:
    row = await get_market_product(session, market_product_id, market_id)
    market = await session.get(Market, market_id)
    require_capability(market, "product_image_override")
    asset = store_flyer_image(
        namespace=f"markets/{market_id}/catalog/{row.id}",
        original_content=content,
        declared_mime_type=mime_type,
    )
    row.image_storage_key = asset.storage_key
    row.image_mime_type = asset.mime_type
    row.image_quality_status = "good"
    await session.commit()
    return await get_market_product(session, market_product_id, market_id)


async def remove_market_product_image(session: AsyncSession, market_product_id: UUID, market_id: UUID) -> None:
    row = await get_market_product(session, market_product_id, market_id)
    market = await session.get(Market, market_id)
    require_capability(market, "product_image_override")
    row.image_storage_key = row.image_url = row.image_mime_type = row.image_quality_status = None
    await session.commit()


async def _lock_market(session: AsyncSession, market_id: UUID) -> Market:
    market = await session.scalar(select(Market).where(Market.id == market_id).with_for_update())
    if market is None:
        raise _not_found("Market")
    return market


async def _validate_scoped_reference(
    session: AsyncSession,
    model: type[Brand] | type[Category],
    item_id: UUID | None,
    market_id: UUID,
    label: str,
) -> Brand | Category | None:
    if item_id is None:
        return None
    row = await session.scalar(
        select(model).where(
            model.id == item_id,
            model.is_active.is_(True),
            or_(
                and_(model.is_global.is_(True), model.market_id.is_(None)),
                and_(model.is_global.is_(False), model.market_id == market_id),
            ),
        )
    )
    if row is None:
        raise _not_found(label)
    return row


def _normalized_market_product_values(values: dict[str, Any]) -> dict[str, Any]:
    data = normalized_package_values(values)
    # MarketProduct calls its legacy display field private_package_size. The
    # shared parser remains authoritative for deriving its structured identity.
    data.pop("package_size", None)
    if data.get("private_package_size"):
        parsed = normalized_package_values({"package_size": data["private_package_size"]})
        if parsed.get("package_amount") is not None and data.get("package_amount") is None:
            data["package_amount"] = parsed["package_amount"]
        if parsed.get("package_unit") is not None and data.get("package_unit") is None:
            data["package_unit"] = parsed["package_unit"]
    if data.get("private_package_type") and not data.get("package_type_canonical"):
        data["package_type_canonical"] = normalize_package_type(data["private_package_type"])
    if data.get("private_barcode"):
        normalized_barcode = normalize_barcode(data["private_barcode"])
        data["private_barcode"] = (
            normalized_barcode
            if normalized_barcode and not normalized_barcode.startswith("raw:")
            else data["private_barcode"].strip()
        )
    if data.get("private_sku"):
        data["private_sku"] = data["private_sku"].strip()
    return data


def _validate_structured_package_pair(values: dict[str, Any]) -> None:
    amount_present = "package_amount" in values
    unit_present = "package_unit" in values
    if not amount_present and not unit_present:
        return
    if amount_present != unit_present or (values.get("package_amount") is None) != (
        values.get("package_unit") is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=("package_amount and package_unit must be provided or cleared together."),
        )


def _enforce_global_match_decision(
    match: CatalogMatchResult,
    *,
    allow_override: bool,
) -> None:
    if any(candidate.already_adopted for candidate in match.candidates):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A matching global product is already adopted by this market.",
        )
    if match.match_type != "none" and not allow_override:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A global catalog match is available. Adopt it or explicitly "
                "continue as a local product."
            ),
        )


async def _ensure_no_local_duplicate(
    session: AsyncSession,
    *,
    market_id: UUID,
    name: str,
    brand: str | None = None,
    barcode: str | None = None,
    sku: str | None = None,
    package_size: str | None = None,
    package_amount: Any = None,
    package_unit: str | None = None,
    package_type: str | None = None,
    exclude_market_product_id: UUID | None = None,
    exclude_product_id: UUID | None = None,
    canonical_product: Product | None = None,
) -> None:
    incoming = _local_identity(
        name=name,
        brand=brand,
        barcode=barcode,
        sku=sku,
        package_size=package_size,
        package_amount=package_amount,
        package_unit=package_unit,
        package_type=package_type,
    )
    market_rows = list(
        (
            await session.scalars(
                select(MarketProduct)
                .options(
                    selectinload(MarketProduct.product).selectinload(Product.brand),
                    selectinload(MarketProduct.product).selectinload(Product.aliases),
                    selectinload(MarketProduct.product)
                    .selectinload(Product.brand)
                    .selectinload(Brand.aliases),
                    selectinload(MarketProduct.product).selectinload(Product.category),
                    selectinload(MarketProduct.legacy_product).selectinload(Product.aliases),
                    selectinload(MarketProduct.legacy_product)
                    .selectinload(Product.brand)
                    .selectinload(Brand.aliases),
                )
                .where(MarketProduct.market_id == market_id)
            )
        ).unique()
    )
    canonical_incoming = (
        _product_identity_variants(canonical_product)
        if canonical_product is not None
        else []
    )
    for row in market_rows:
        if row.id == exclude_market_product_id or (
            exclude_product_id is not None and row.legacy_product_id == exclude_product_id
        ):
            continue
        for existing in _market_product_identity_variants(row, market_id):
            _raise_if_local_duplicate(incoming, existing)
            for canonical_identity in canonical_incoming:
                _raise_if_local_duplicate(canonical_identity, existing)

    linked_legacy_ids = select(MarketProduct.legacy_product_id).where(
        MarketProduct.market_id == market_id,
        MarketProduct.legacy_product_id.is_not(None),
    )
    statement = (
        select(Product)
        .options(
            selectinload(Product.aliases),
            selectinload(Product.brand).selectinload(Brand.aliases),
        )
        .where(
            Product.market_id == market_id,
            Product.is_global.is_(False),
            Product.id.not_in(linked_legacy_ids),
        )
    )
    if exclude_product_id is not None:
        statement = statement.where(Product.id != exclude_product_id)
    for product in (await session.scalars(statement)).unique():
        for existing in _product_identity_variants(product):
            _raise_if_local_duplicate(incoming, existing)


def _effective_global_identity(
    product: Product | None,
    values: dict[str, Any],
) -> dict[str, Any]:
    if product is None:
        raise ValueError("A global product is required for effective identity checks.")
    has_package_override = (
        values.get("package_amount") is not None and values.get("package_unit") is not None
    )
    return {
        "name": values.get("display_name_override") or product.name,
        "brand": values.get("private_brand_text")
        or (product.brand.name if product.brand else None),
        "barcode": values.get("private_barcode") or product.barcode,
        "sku": values.get("private_sku"),
        "package_size": values.get("private_package_size") or product.package_size,
        "package_amount": values.get("package_amount")
        if has_package_override
        else product.package_amount,
        "package_unit": values.get("package_unit")
        if has_package_override
        else product.package_unit,
        "package_type": values.get("package_type_canonical")
        or values.get("private_package_type")
        or product.package_type_canonical
        or product.package_type,
    }


def _product_identity_variants(product: Product) -> list[dict[str, str | None]]:
    names = [product.name, *(alias.alias for alias in product.aliases)]
    brands: list[str | None] = [None]
    if product.brand is not None:
        brands = [
            product.brand.name,
            *(alias.alias for alias in product.brand.aliases),
        ]
    identities = [
        _local_identity(
            name=name,
            brand=brand,
            barcode=product.barcode,
            package_size=product.package_size,
            package_amount=product.package_amount,
            package_unit=product.package_unit,
            package_type=product.package_type_canonical or product.package_type,
        )
        for name in dict.fromkeys(names)
        for brand in dict.fromkeys(brands)
    ]
    return _unique_identities(identities)


def _market_product_identity_variants(
    row: MarketProduct,
    market_id: UUID,
) -> list[dict[str, str | None]]:
    if row.product_id is not None:
        if not _is_shared_product(row.product):
            return []
        values = {
            "display_name_override": row.display_name_override,
            "private_brand_text": row.private_brand_text,
            "private_barcode": row.private_barcode,
            "private_sku": row.private_sku,
            "private_package_size": row.private_package_size,
            "private_package_type": row.private_package_type,
            "package_amount": row.package_amount,
            "package_unit": row.package_unit,
            "package_type_canonical": row.package_type_canonical,
        }
        return _unique_identities(
            [
                _local_identity(**_effective_global_identity(row.product, values)),
                *_product_identity_variants(row.product),
            ]
        )

    legacy = row.legacy_product
    if not _is_local_legacy_product(legacy, market_id):
        legacy = None
    has_structured_package = row.package_amount is not None and row.package_unit is not None
    effective = _local_identity(
        name=row.display_name_override or row.private_name or (legacy.name if legacy else ""),
        brand=row.private_brand_text or (legacy.brand.name if legacy and legacy.brand else None),
        barcode=row.private_barcode or (legacy.barcode if legacy else None),
        sku=row.private_sku,
        package_size=row.private_package_size or (legacy.package_size if legacy else None),
        package_amount=row.package_amount
        if has_structured_package
        else (legacy.package_amount if legacy else None),
        package_unit=row.package_unit
        if has_structured_package
        else (legacy.package_unit if legacy else None),
        package_type=row.package_type_canonical
        or row.private_package_type
        or (legacy.package_type_canonical or legacy.package_type if legacy else None),
    )
    return _unique_identities(
        [
            effective,
            *(_product_identity_variants(legacy) if legacy is not None else []),
        ]
    )


def _unique_identities(
    identities: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    return list({tuple(identity.items()): identity for identity in identities}.values())


def _local_identity(
    *,
    name: str,
    brand: str | None,
    barcode: str | None,
    package_size: str | None,
    package_amount: Any,
    package_unit: str | None,
    package_type: str | None,
    sku: str | None = None,
) -> dict[str, str | None]:
    return {
        "name": canonical_name_key(name, brand),
        "brand": normalize_words(brand),
        "barcode": _duplicate_barcode_key(barcode),
        "sku": sku.strip().casefold() if sku and sku.strip() else None,
        "package": canonical_package_key(
            amount=package_amount,
            unit=package_unit,
            package_size=package_size,
            fallback_name=name,
        ),
        "package_type": normalize_package_type(package_type),
    }


def _duplicate_barcode_key(value: str | None) -> str | None:
    normalized = normalize_barcode(value)
    if normalized:
        return normalized if normalized.startswith("raw:") else f"digits:{normalized}"
    if value and value.strip():
        return f"raw:{value.strip().casefold()}"
    return None


def _raise_if_local_duplicate(
    incoming: dict[str, str | None], existing: dict[str, str | None]
) -> None:
    if incoming["barcode"] and incoming["barcode"] == existing["barcode"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Barcode is already used by a product in this market.",
        )
    if incoming["sku"] and incoming["sku"] == existing["sku"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU is already used by a product in this market.",
        )
    same_type = (
        not incoming["package_type"]
        or not existing["package_type"]
        or incoming["package_type"] == existing["package_type"]
    )
    distinct_explicit_identity = bool(
        (incoming["barcode"] and existing["barcode"] and incoming["barcode"] != existing["barcode"])
        or (incoming["sku"] and existing["sku"] and incoming["sku"] != existing["sku"])
    )
    if (
        _same_canonical_name_and_brand(incoming, existing)
        and incoming["package"] == existing["package"]
        and same_type
        and not distinct_explicit_identity
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this canonical identity already exists in this market.",
        )


def _same_canonical_name_and_brand(
    incoming: dict[str, str | None], existing: dict[str, str | None]
) -> bool:
    incoming_name, existing_name = incoming["name"], existing["name"]
    incoming_brand, existing_brand = incoming["brand"], existing["brand"]
    if not incoming_name or not existing_name:
        return False
    if incoming_name == existing_name:
        return not incoming_brand or not existing_brand or incoming_brand == existing_brand
    if incoming_brand and not existing_brand:
        return existing_name == f"{incoming_brand} {incoming_name}"
    if existing_brand and not incoming_brand:
        return incoming_name == f"{existing_brand} {existing_name}"
    return False


def _add_catalog_activity(
    session: AsyncSession,
    *,
    market_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        ActivityLog(
            market_id=market_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            description=action.replace("_", " "),
            metadata_=metadata or {},
        )
    )


def _is_shared_product(product: Product | None) -> bool:
    if product is None or not product.is_global or product.market_id is not None:
        return False
    if product.brand is not None and (
        not product.brand.is_global or product.brand.market_id is not None
    ):
        return False
    return not (
        product.category is not None
        and (not product.category.is_global or product.category.market_id is not None)
    )


def _is_visible_category(category: Category | None, market_id: UUID) -> bool:
    if category is None:
        return True
    return (category.is_global and category.market_id is None) or (
        not category.is_global and category.market_id == market_id
    )


def _is_local_legacy_product(product: Product | None, market_id: UUID) -> bool:
    return bool(product is not None and not product.is_global and product.market_id == market_id)


def _global_mutation_forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Global catalog records are platform-managed.")
