import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_catalog_session, get_current_platform_admin
from app.models import Brand, Category, MarketProduct, PlatformAdmin, Product, ProductAlias, ProductImage
from app.schemas.common import ListResponse
from app.schemas.platform_catalog import (
    PlatformBrandCreate, PlatformBrandRead, PlatformBrandUpdate, PlatformBulkImageResolution,
    PlatformCategoryCreate, PlatformCategoryRead, PlatformCategoryUpdate, PlatformImageIdsPayload,
    PlatformProductCreate, PlatformProductRead, PlatformProductUpdate,
)
from app.services.catalog import normalize_alias, slugify
from app.services.global_catalog_excel import COLUMNS, MAX_ROWS, build_template, parse_workbook
from app.services.global_catalog_bulk_images import (
    BulkImportError,
    extract_zip,
    import_bulk_rows,
    match_bulk_rows,
    read_bounded_zip_body,
)
from app.services.image_pipeline import read_bounded_image_body, require_supported_image_mime_type, store_flyer_image
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


async def _product_usage_counts(session, column, item_ids):
    if not item_ids:
        return {}
    result = await session.execute(select(column, func.count(Product.id)).where(column.in_(item_ids)).group_by(column))
    return {item_id: int(count) for item_id, count in result.all()}


async def _market_product_usage_counts(session, product_ids):
    if not product_ids:
        return {}
    result = await session.execute(select(MarketProduct.product_id, func.count(MarketProduct.id)).where(MarketProduct.product_id.in_(product_ids)).group_by(MarketProduct.product_id))
    return {product_id: int(count) for product_id, count in result.all()}


@router.get("/categories", response_model=ListResponse[PlatformCategoryRead])
async def list_categories(search: str | None = None, is_active: bool | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    conditions = [Category.is_global.is_(True)]
    if search: conditions.append(Category.name.ilike(f"%{search}%"))
    if is_active is not None: conditions.append(Category.is_active.is_(is_active))
    rows = list((await session.scalars(select(Category).where(*conditions).order_by(Category.sort_order, Category.name).limit(limit).offset(offset))).all())
    total = await session.scalar(select(func.count()).select_from(Category).where(*conditions)) or 0
    usage_counts = await _product_usage_counts(session, Product.category_id, [row.id for row in rows])
    items = []
    for row in rows:
        item = PlatformCategoryRead.model_validate(row, from_attributes=True).model_dump()
        item["usage_count"] = usage_counts.get(row.id, 0)
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
    row.is_active = False; await session.commit(); return row


@router.get("/brands", response_model=ListResponse[PlatformBrandRead])
async def list_brands(search: str | None = None, is_active: bool | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    conditions = [Brand.is_global.is_(True)]
    if search: conditions.append(Brand.name.ilike(f"%{search}%"))
    if is_active is not None: conditions.append(Brand.is_active.is_(is_active))
    rows = list((await session.scalars(select(Brand).where(*conditions).order_by(Brand.name).limit(limit).offset(offset))).all())
    total = await session.scalar(select(func.count()).select_from(Brand).where(*conditions)) or 0
    usage_counts = await _product_usage_counts(session, Product.brand_id, [row.id for row in rows])
    items = []
    for row in rows:
        item = PlatformBrandRead.model_validate(row, from_attributes=True).model_dump()
        item["usage_count"] = usage_counts.get(row.id, 0)
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
    usage_counts = await _market_product_usage_counts(session, [row.id for row in rows])
    for row in rows: row.usage_count = usage_counts.get(row.id, 0)
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
    mime_type = require_supported_image_mime_type(request.headers.get("content-type", ""))
    content = await read_bounded_image_body(request)
    asset = store_flyer_image(
        namespace=f"global/catalog/{row.id}",
        original_content=content,
        declared_mime_type=mime_type,
    )
    if primary: await session.execute(ProductImage.__table__.update().where(ProductImage.product_id == row.id).values(is_primary=False))
    image = ProductImage(
        product_id=row.id,
        storage_key=asset.storage_key,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        width=asset.width,
        height=asset.height,
        has_transparent_background=asset.has_alpha,
        quality_status="needs_review",
        is_primary=primary,
    )
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
    await session.delete(image); await session.commit()


async def _global_image(session, product_id: UUID, image_id: UUID) -> ProductImage:
    await _global(session, Product, product_id)
    image = await session.scalar(select(ProductImage).where(ProductImage.id == image_id, ProductImage.product_id == product_id))
    if image is None:
        raise HTTPException(404, "Image not found.")
    return image


@router.patch("/products/{product_id}/images/{image_id}/approve", response_model=dict)
async def approve_image(product_id: UUID, image_id: UUID, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    image = await _global_image(session, product_id, image_id)
    image.quality_status = "good"
    await session.commit()
    return {"id": image.id, "product_id": product_id, "quality_status": image.quality_status}


@router.patch("/products/{product_id}/images/{image_id}/reject", response_model=dict)
async def reject_image(product_id: UUID, image_id: UUID, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    image = await _global_image(session, product_id, image_id)
    image.quality_status = "rejected"
    if image.is_primary:
        image.is_primary = False
    await session.commit()
    return {"id": image.id, "product_id": product_id, "quality_status": image.quality_status}


async def _bulk_set_quality_status(session: AsyncSession, image_ids: list[UUID], quality_status: str) -> dict:
    rows = list(
        (
            await session.scalars(
                select(ProductImage)
                .join(Product, Product.id == ProductImage.product_id)
                .where(ProductImage.id.in_(image_ids), Product.is_global.is_(True))
            )
        ).all()
    )
    found_ids = {row.id for row in rows}
    for row in rows:
        row.quality_status = quality_status
        if quality_status == "rejected" and row.is_primary:
            row.is_primary = False
    await session.commit()
    return {
        "updated": len(rows),
        "quality_status": quality_status,
        "not_found": [str(image_id) for image_id in image_ids if image_id not in found_ids],
    }


@router.post("/products/images/bulk-approve", response_model=dict)
async def bulk_approve_images(payload: PlatformImageIdsPayload, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    return await _bulk_set_quality_status(session, payload.image_ids, "good")


@router.post("/products/images/bulk-reject", response_model=dict)
async def bulk_reject_images(payload: PlatformImageIdsPayload, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    return await _bulk_set_quality_status(session, payload.image_ids, "rejected")


@router.post("/products/bulk-images/preview", response_model=dict)
async def bulk_images_preview(request: Request, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    content = await read_bounded_zip_body(request)
    try:
        package = extract_zip(content)
    except BulkImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    rows = await match_bulk_rows(session, package.manifest_rows, package.images)
    counts = {"total": len(rows)}
    for key in ("exact_match", "matched", "ambiguous", "unmatched", "invalid", "error"):
        counts[key] = sum(1 for row in rows if row.status == key)
    return {"counts": counts, "rows": [row.to_dict() for row in rows]}


@router.post("/products/bulk-images/import", response_model=dict)
async def bulk_images_import(request: Request, resolutions: str | None = Query(default=None), _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    content = await read_bounded_zip_body(request)
    try:
        package = extract_zip(content)
    except BulkImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    resolved: dict[int, UUID] = {}
    if resolutions:
        try:
            raw_entries = json.loads(resolutions)
            if not isinstance(raw_entries, list):
                raise ValueError("resolutions must be a JSON array.")
            parsed = [PlatformBulkImageResolution.model_validate(entry) for entry in raw_entries]
        except (json.JSONDecodeError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid resolutions payload: {exc}") from None
        resolved = {entry.row_index: entry.product_id for entry in parsed}

    rows = await match_bulk_rows(session, package.manifest_rows, package.images)
    summary = await import_bulk_rows(session, rows, package.images, resolved)
    return summary.to_dict()

@router.get("/products/import-template", response_class=Response)
async def download_product_import_template(_: PlatformAdmin = admin):
    return Response(
        content=build_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="leafletpilot-global-products-template.xlsx"'},
    )


async def _read_xlsx(request: Request) -> bytes:
    if request.headers.get("content-type", "").split(";", 1)[0] not in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"
    }:
        raise HTTPException(415, "Yalnızca .xlsx dosyaları kabul edilir.")
    size = int(request.headers.get("content-length") or 0)
    if size > 10 * 1024 * 1024:
        raise HTTPException(413, "Excel dosyası en fazla 10 MiB olabilir.")
    content = await request.body()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Excel dosyası en fazla 10 MiB olabilir.")
    return content


async def _excel_preview(content: bytes, session: AsyncSession) -> list[dict]:
    rows = parse_workbook(content)
    valid = [row for row in rows if row.get("status") != "invalid"]
    barcodes = {row["barcode_sku"] for row in valid if row["barcode_sku"]}
    names = {row["canonical_name"].casefold() for row in valid}
    existing = list((await session.scalars(select(Product).where(Product.is_global.is_(True), or_(Product.barcode.in_(barcodes) if barcodes else False, func.lower(Product.name).in_(names) if names else False)))).all())
    by_barcode = {product.barcode: product for product in existing if product.barcode}
    by_name = {product.name.casefold(): product for product in existing}
    brands = {brand.name.casefold(): brand for brand in (await session.scalars(select(Brand).where(Brand.is_global.is_(True)))).all()}
    categories = {category.name.casefold(): category for category in (await session.scalars(select(Category).where(Category.is_global.is_(True)))).all()}
    seen_barcodes: set[str] = set()
    for row in rows:
        if row.get("status") == "invalid": continue
        barcode = row["barcode_sku"]
        if barcode and barcode in seen_barcodes:
            row.update(status="conflict", error="Dosyada aynı barkod/SKU birden fazla kez bulunuyor."); continue
        seen_barcodes.add(barcode)
        if row["brand"] and row["brand"].casefold() not in brands:
            row.update(status="invalid", error="Global marka bulunamadı."); continue
        if row["category"] and row["category"].casefold() not in categories:
            row.update(status="invalid", error="Global kategori bulunamadı."); continue
        by_code = by_barcode.get(barcode) if barcode else None
        by_label = by_name.get(row["canonical_name"].casefold())
        if by_code and by_label and by_code.id != by_label.id:
            row.update(status="ambiguous", error="Barkod ve ürün adı farklı global ürünlerle eşleşiyor."); continue
        match = by_code or by_label
        row["product_id"] = str(match.id) if match else None
        if not match: row["status"] = "new"
        elif (match.name == row["canonical_name"] and (match.barcode or "") == barcode and (match.package_size or "") == row["package_size"] and (match.package_type or "") == row["package_type"] and match.is_active == row["active"]): row["status"] = "unchanged"
        else: row["status"] = "update"
        row["aliases"] = [item.strip() for item in row["aliases"].split(";") if item.strip()]
    return rows


@router.post("/products/import/preview", response_model=dict)
async def preview_product_import(request: Request, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    rows = await _excel_preview(await _read_xlsx(request), session)
    counts = {name: sum(row.get("status") == name for row in rows) for name in ("new", "update", "unchanged", "invalid", "ambiguous", "conflict")}
    return {"rows": rows, "counts": {"total": len(rows), **counts, "with_image": sum(bool(row.get("image_filename")) for row in rows)}}


@router.post("/products/import", response_model=dict)
async def import_products(request: Request, _: PlatformAdmin = admin, session: AsyncSession = Depends(get_catalog_session)):
    rows = await _excel_preview(await _read_xlsx(request), session)
    brands = {brand.name.casefold(): brand for brand in (await session.scalars(select(Brand).where(Brand.is_global.is_(True)))).all()}
    categories = {category.name.casefold(): category for category in (await session.scalars(select(Category).where(Category.is_global.is_(True)))).all()}
    result = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "images_awaiting_review": 0, "rows": []}
    for row in rows:
        if row["status"] in {"invalid", "ambiguous", "conflict"}:
            result["skipped"] += 1; result["rows"].append(row); continue
        if row["status"] == "unchanged": result["unchanged"] += 1; result["rows"].append(row); continue
        product = await session.get(Product, UUID(row["product_id"])) if row.get("product_id") else None
        values = dict(name=row["canonical_name"], barcode=row["barcode_sku"] or None, package_size=row["package_size"] or None, package_type=row["package_type"] or None, is_active=row["active"], brand_id=brands[row["brand"].casefold()].id if row["brand"] else None, category_id=categories[row["category"].casefold()].id if row["category"] else None)
        if product is None:
            product = Product(**values, is_global=True, market_id=None); session.add(product); result["created"] += 1
        else:
            for key, value in values.items(): setattr(product, key, value)
            result["updated"] += 1
        product.aliases = [ProductAlias(alias=alias, normalized_alias=normalize_alias(alias), source="platform_import") for alias in row.get("aliases", [])]
        result["rows"].append(row)
    await session.commit()
    return {"total": len(rows), **result}
