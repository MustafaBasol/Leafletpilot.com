from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_catalog_session, get_current_platform_admin
from app.models import Brand, Category, MarketProduct, PlatformAdmin, Product, ProductAlias, ProductImage
from app.schemas.common import ListResponse
from app.schemas.platform_catalog import (
    PlatformBrandCreate, PlatformBrandRead, PlatformBrandUpdate, PlatformCategoryCreate,
    PlatformCategoryRead, PlatformCategoryUpdate, PlatformProductCreate, PlatformProductRead,
    PlatformProductUpdate,
)
from app.services.catalog import normalize_alias, slugify
from app.services.rendering import storage_path_for_key

router = APIRouter(prefix="/platform/catalog", tags=["platform-catalog"])
admin = Depends(get_current_platform_admin)


def _conflict(detail="Catalog record conflicts with existing data."):
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def _global(session, model, item_id):
    item = await session.scalar(select(model).where(model.id == item_id, model.is_global.is_(True)))
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found.")
    return item


async def _count_products(session, column, item_id):
    return int(await session.scalar(select(func.count(Product.id)).where(column == item_id)) or 0)


@router.get("/categories", response_model=ListResponse[PlatformCategoryRead])
async def list_categories(search: str | None = None, is_active: bool | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    conditions = [Category.is_global.is_(True)]
    if search: conditions.append(Category.name.ilike(f"%{search}%"))
    if is_active is not None: conditions.append(Category.is_active.is_(is_active))
    rows = list((await session.scalars(select(Category).where(*conditions).order_by(Category.sort_order, Category.name).limit(limit).offset(offset))).all())
    total = await session.scalar(select(func.count()).select_from(Category).where(*conditions)) or 0
    items = []
    for row in rows:
        item = PlatformCategoryRead.model_validate(row, from_attributes=True).model_dump()
        item["usage_count"] = await _count_products(session, Product.category_id, row.id)
        items.append(item)
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/categories", response_model=PlatformCategoryRead, status_code=201)
async def create_category(payload: PlatformCategoryCreate, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    if await session.scalar(select(Category).where(Category.is_global.is_(True), func.lower(Category.name) == payload.name.lower())):
        raise _conflict("A global category with this name already exists.")
    data = payload.model_dump(); data["slug"] = payload.slug or slugify(payload.name)
    row = Category(**data, is_global=True, market_id=None)
    session.add(row)
    try: await session.commit()
    except Exception as exc:
        await session.rollback(); raise _conflict() from exc
    return row


@router.patch("/categories/{category_id}", response_model=PlatformCategoryRead)
async def update_category(category_id: UUID, payload: PlatformCategoryUpdate, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    row = await _global(session, Category, category_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and await session.scalar(select(Category).where(Category.id != category_id, Category.is_global.is_(True), func.lower(Category.name) == data["name"].lower())):
        raise _conflict("A global category with this name already exists.")
    for key, value in data.items(): setattr(row, key, value)
    await session.commit(); return row


@router.delete("/categories/{category_id}", response_model=PlatformCategoryRead)
async def deactivate_category(category_id: UUID, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    row = await _global(session, Category, category_id)
    if await _count_products(session, Product.category_id, category_id):
        raise _conflict("Category is referenced by products; deactivate it instead of deleting it.")
    row.is_active = False; await session.commit(); return row


@router.get("/brands", response_model=ListResponse[PlatformBrandRead])
async def list_brands(search: str | None = None, is_active: bool | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    conditions = [Brand.is_global.is_(True)]
    if search: conditions.append(Brand.name.ilike(f"%{search}%"))
    if is_active is not None: conditions.append(Brand.is_active.is_(is_active))
    rows = list((await session.scalars(select(Brand).where(*conditions).order_by(Brand.name).limit(limit).offset(offset))).all())
    total = await session.scalar(select(func.count()).select_from(Brand).where(*conditions)) or 0
    items = []
    for row in rows:
        item = PlatformBrandRead.model_validate(row, from_attributes=True).model_dump()
        item["usage_count"] = await _count_products(session, Product.brand_id, row.id)
        items.append(item)
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/brands", response_model=PlatformBrandRead, status_code=201)
async def create_brand(payload: PlatformBrandCreate, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    duplicate = await session.scalar(select(Brand).where(Brand.is_global.is_(True), func.lower(Brand.name) == payload.name.lower()))
    if duplicate: raise _conflict("A global brand with this name already exists.")
    data = payload.model_dump(); data["slug"] = payload.slug or slugify(payload.name)
    row = Brand(**data, is_global=True, market_id=None)
    session.add(row)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback(); raise _conflict() from exc
    return row


@router.patch("/brands/{brand_id}", response_model=PlatformBrandRead)
async def update_brand(brand_id: UUID, payload: PlatformBrandUpdate, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    row = await _global(session, Brand, brand_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and await session.scalar(select(Brand).where(Brand.id != brand_id, Brand.is_global.is_(True), func.lower(Brand.name) == data["name"].lower())): raise _conflict("A global brand with this name already exists.")
    for key, value in data.items(): setattr(row, key, value)
    await session.commit(); return row


@router.delete("/brands/{brand_id}", response_model=PlatformBrandRead)
async def deactivate_brand(brand_id: UUID, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    row = await _global(session, Brand, brand_id); row.is_active = False; await session.commit(); return row


def _product_read(row):
    return PlatformProductRead(
        id=row.id,
        market_id=row.market_id,
        brand_id=row.brand_id,
        category_id=row.category_id,
        name=row.name,
        short_name=row.short_name,
        barcode=row.barcode,
        package_size=row.package_size,
        package_type=row.package_type,
        sort_order=row.sort_order,
        is_global=row.is_global,
        is_active=row.is_active,
        quality_score=row.quality_score,
        usage_count=row.usage_count or 0,
        aliases=[
            {
                "id": alias.id,
                "product_id": alias.product_id,
                "alias": alias.alias,
                "normalized_alias": alias.normalized_alias,
                "source": alias.source,
                "created_at": alias.created_at,
            }
            for alias in row.aliases
        ],
        images=[
            {
                "id": image.id,
                "product_id": image.product_id,
                "image_type": image.image_type,
                "mime_type": image.mime_type,
                "size_bytes": image.size_bytes,
                "width": image.width,
                "height": image.height,
                "has_transparent_background": image.has_transparent_background,
                "quality_status": image.quality_status,
                "is_primary": image.is_primary,
                "created_at": image.created_at,
                "preview_url": f"/api/platform/catalog/products/{row.id}/images/{image.id}/content",
            }
            for image in row.images
        ],
    )


@router.get("/products", response_model=ListResponse[PlatformProductRead])
async def list_products(search: str | None = None, barcode: str | None = None, brand_id: UUID | None = None, category_id: UUID | None = None, is_active: bool | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    conditions = [Product.is_global.is_(True)]
    if search: conditions.append(or_(Product.name.ilike(f"%{search}%"), Product.short_name.ilike(f"%{search}%"), Product.aliases.any(ProductAlias.normalized_alias.ilike(f"%{normalize_alias(search)}%"))))
    if barcode: conditions.append(Product.barcode.ilike(f"%{barcode}%"))
    if brand_id: conditions.append(Product.brand_id == brand_id)
    if category_id: conditions.append(Product.category_id == category_id)
    if is_active is not None: conditions.append(Product.is_active.is_(is_active))
    statement = select(Product).options(selectinload(Product.aliases), selectinload(Product.images)).where(*conditions).order_by(Product.name)
    rows = list((await session.scalars(statement.limit(limit).offset(offset))).unique().all())
    total = await session.scalar(select(func.count()).select_from(Product).where(*conditions)) or 0
    for row in rows: row.usage_count = await session.scalar(select(func.count(MarketProduct.id)).where(MarketProduct.product_id == row.id)) or 0
    return ListResponse(items=[_product_read(row) for row in rows], total=total, limit=limit, offset=offset)


@router.post("/products", response_model=PlatformProductRead, status_code=201)
async def create_product(payload: PlatformProductCreate, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    if payload.barcode and await session.scalar(select(Product).where(Product.is_global.is_(True), Product.barcode == payload.barcode)): raise _conflict("A global product with this barcode already exists.")
    if await session.scalar(select(Product).where(Product.is_global.is_(True), func.lower(Product.name) == payload.name.lower())): raise _conflict("A global product with this name already exists.")
    data = payload.model_dump(exclude={"aliases"}); row = Product(**data, is_global=True, market_id=None)
    row.aliases = [ProductAlias(alias=a.alias, normalized_alias=normalize_alias(a.alias), source=a.source) for a in payload.aliases]
    session.add(row); await session.commit()
    row = await session.scalar(select(Product).options(selectinload(Product.aliases), selectinload(Product.images)).where(Product.id == row.id))
    return _product_read(row)


@router.patch("/products/{product_id}", response_model=PlatformProductRead)
async def update_product(product_id: UUID, payload: PlatformProductUpdate, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    await _global(session, Product, product_id)
    row = await session.scalar(select(Product).options(selectinload(Product.aliases), selectinload(Product.images)).where(Product.id == product_id))
    data = payload.model_dump(exclude_unset=True, exclude={"aliases"})
    if "barcode" in data and data["barcode"] and await session.scalar(select(Product).where(Product.id != product_id, Product.is_global.is_(True), Product.barcode == data["barcode"])): raise _conflict("A global product with this barcode already exists.")
    if "name" in data and data["name"] and await session.scalar(select(Product).where(Product.id != product_id, Product.is_global.is_(True), func.lower(Product.name) == data["name"].lower())): raise _conflict("A global product with this name already exists.")
    for key, value in data.items(): setattr(row, key, value)
    if payload.aliases is not None:
        row.aliases = [ProductAlias(alias=a.alias, normalized_alias=normalize_alias(a.alias), source=a.source) for a in payload.aliases]
    await session.commit()
    row = await session.scalar(select(Product).options(selectinload(Product.aliases), selectinload(Product.images)).where(Product.id == row.id))
    return _product_read(row)


@router.delete("/products/{product_id}", response_model=PlatformProductRead)
async def deactivate_product(product_id: UUID, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    await _global(session, Product, product_id)
    row = await session.scalar(select(Product).options(selectinload(Product.aliases), selectinload(Product.images)).where(Product.id == product_id))
    row.is_active = False
    await session.commit()
    return _product_read(row)


@router.post("/products/{product_id}/images", response_model=dict, status_code=201)
async def upload_image(product_id: UUID, request: Request, primary: bool = False, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    row = await _global(session, Product, product_id)
    allowed = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
    mime_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if mime_type not in allowed: raise HTTPException(415, "Only PNG, JPEG, and WebP images are allowed.")
    content = await request.body()
    signatures = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}
    if len(content) > 10 * 1024 * 1024: raise HTTPException(413, "Image must be 10 MiB or smaller.")
    if not content.startswith(signatures[mime_type]) or (mime_type == "image/webp" and content[8:12] != b"WEBP"):
        raise HTTPException(422, "Image signature does not match the declared MIME type.")
    key = f"global/catalog/{row.id}/{uuid4()}{allowed[mime_type]}"
    path = storage_path_for_key(key); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    if primary: await session.execute(ProductImage.__table__.update().where(ProductImage.product_id == row.id).values(is_primary=False))
    image = ProductImage(product_id=row.id, storage_key=key, mime_type=mime_type, size_bytes=len(content), quality_status="needs_review", is_primary=primary)
    session.add(image); await session.commit(); await session.refresh(image)
    return {"id": image.id, "product_id": row.id, "mime_type": image.mime_type, "size_bytes": image.size_bytes, "is_primary": image.is_primary}


@router.patch("/products/{product_id}/images/{image_id}/primary", response_model=dict)
async def set_primary_image(product_id: UUID, image_id: UUID, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    await _global(session, Product, product_id)
    image = await session.scalar(select(ProductImage).where(ProductImage.id == image_id, ProductImage.product_id == product_id))
    if image is None:
        raise HTTPException(404, "Image not found.")
    await session.execute(ProductImage.__table__.update().where(ProductImage.product_id == product_id).values(is_primary=False))
    image.is_primary = True
    await session.commit()
    return {"id": image.id, "product_id": product_id, "mime_type": image.mime_type, "size_bytes": image.size_bytes, "is_primary": True}


@router.get("/products/{product_id}/images/{image_id}/content", include_in_schema=False)
async def image_content(product_id: UUID, image_id: UUID, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    await _global(session, Product, product_id)
    image = await session.scalar(select(ProductImage).where(ProductImage.id == image_id, ProductImage.product_id == product_id))
    if image is None or not image.storage_key:
        raise HTTPException(404, "Image not found.")
    path = storage_path_for_key(image.storage_key)
    if not path.is_file():
        raise HTTPException(404, "Image file not found.")
    return FileResponse(path, media_type=image.mime_type or "application/octet-stream")


@router.delete("/products/{product_id}/images/{image_id}", status_code=204)
async def remove_image(product_id: UUID, image_id: UUID, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    await _global(session, Product, product_id); image = await session.scalar(select(ProductImage).where(ProductImage.id == image_id, ProductImage.product_id == product_id))
    if image is None: raise HTTPException(404, "Image not found.")
    if image.storage_key:
        path = storage_path_for_key(image.storage_key)
        if path.exists(): path.unlink()
    await session.delete(image); await session.commit()
