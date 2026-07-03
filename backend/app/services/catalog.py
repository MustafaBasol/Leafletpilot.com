import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Brand, Category, Product, ProductAlias, ProductImage
from app.schemas.brand import BrandCreate, BrandUpdate
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.schemas.product import ProductAliasCreate, ProductCreate, ProductUpdate

PUNCTUATION_RE = re.compile(r"[!\"#$%&'()*+,./:;<=>?@\[\\\]^_`{|}~-]+")
SPACES_RE = re.compile(r"\s+")


def slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = PUNCTUATION_RE.sub(" ", slug)
    slug = SPACES_RE.sub("-", slug).strip("-")
    return slug or "item"


def normalize_alias(value: str) -> str:
    # Turkish characters are intentionally preserved for MVP matching fidelity.
    normalized = value.strip().lower()
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    return SPACES_RE.sub(" ", normalized).strip()


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
        statement = statement.where(Brand.name.ilike(f"%{search}%"))
    if is_active is not None:
        statement = statement.where(Brand.is_active.is_(is_active))
    if is_global is not None:
        statement = statement.where(Brand.is_global.is_(is_global))

    return await _list(session, statement.order_by(Brand.name), limit, offset)


async def create_brand(session: AsyncSession, payload: BrandCreate, market_id: UUID | None) -> Brand:
    data = payload.model_dump()
    data["slug"] = data["slug"] or slugify(data["name"])
    data["market_id"] = resolve_market_scope(data["is_global"], market_id)
    brand = Brand(**data)
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
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, key, value)
    return await _persist(session, brand)


async def delete_brand(session: AsyncSession, brand_id: UUID, market_id: UUID | None) -> Brand:
    brand = await get_brand(session, brand_id, market_id)
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
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, key, value)
    return await _persist(session, category)


async def delete_category(session: AsyncSession, category_id: UUID, market_id: UUID | None) -> Category:
    category = await get_category(session, category_id, market_id)
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

    return await _list(session, statement.order_by(Product.name), limit, offset)


async def create_product(
    session: AsyncSession,
    payload: ProductCreate,
    market_id: UUID | None,
) -> Product:
    data = payload.model_dump(exclude={"aliases", "images"})
    data["market_id"] = resolve_market_scope(data["is_global"], market_id)
    product = Product(**data)
    product.aliases = [_build_alias(alias) for alias in payload.aliases]
    product.images = [ProductImage(**image.model_dump()) for image in payload.images]
    return await _persist(session, product)


async def get_product(session: AsyncSession, product_id: UUID, market_id: UUID | None) -> Product:
    statement = (
        select(Product)
        .options(selectinload(Product.aliases), selectinload(Product.images))
        .where(Product.id == product_id)
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
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    return await _persist(session, product)


async def delete_product(session: AsyncSession, product_id: UUID, market_id: UUID | None) -> Product:
    product = await get_product(session, product_id, market_id)
    product.is_active = False
    return await _persist(session, product)


async def create_product_alias(
    session: AsyncSession,
    product_id: UUID,
    payload: ProductAliasCreate,
    market_id: UUID | None,
) -> ProductAlias:
    product = await get_product(session, product_id, market_id)
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


def _not_found(label: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found.")
