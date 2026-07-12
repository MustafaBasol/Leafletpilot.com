from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Market, MarketProduct

from app.api.deps import get_catalog_session, get_current_market_id, require_market_role
from app.core.roles import MARKET_MUTATION_ROLES
from app.schemas.brand import BrandCreate, BrandRead, BrandUpdate
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.common import ListResponse
from app.schemas.market_product import (
    MarketProductAdoptCreate, MarketProductRead, MarketProductUpdate, PrivateMarketProductCreate,
    ResolvedMarketProductRead, SharedCatalogProductRead,
)
from app.schemas.product import ProductAliasCreate, ProductAliasRead, ProductCreate, ProductRead, ProductUpdate
from app.services import catalog as catalog_service

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/brands", response_model=ListResponse[BrandRead])
async def list_brands(
    search: str | None = None,
    is_active: bool | None = None,
    is_global: bool | None = None,
    include_global: bool = True,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[BrandRead]:
    items, total = await catalog_service.list_brands(
        session,
        market_id=market_id,
        include_global=include_global,
        search=search,
        is_active=is_active,
        is_global=is_global,
        limit=limit,
        offset=offset,
    )
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/brands", response_model=BrandRead, status_code=status.HTTP_201_CREATED)
async def create_brand(
    payload: BrandCreate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> BrandRead:
    return await catalog_service.create_brand(session, payload, market_id)


@router.get("/brands/{brand_id}", response_model=BrandRead)
async def get_brand(
    brand_id: UUID,
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> BrandRead:
    return await catalog_service.get_brand(session, brand_id, market_id)


@router.patch("/brands/{brand_id}", response_model=BrandRead)
async def update_brand(
    brand_id: UUID,
    payload: BrandUpdate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> BrandRead:
    return await catalog_service.update_brand(session, brand_id, payload, market_id)


@router.delete("/brands/{brand_id}", response_model=BrandRead)
async def delete_brand(
    brand_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> BrandRead:
    return await catalog_service.delete_brand(session, brand_id, market_id)


@router.get("/categories", response_model=ListResponse[CategoryRead])
async def list_categories(
    search: str | None = None,
    parent_id: UUID | None = None,
    is_active: bool | None = None,
    is_global: bool | None = None,
    include_global: bool = True,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[CategoryRead]:
    items, total = await catalog_service.list_categories(
        session,
        market_id=market_id,
        include_global=include_global,
        search=search,
        parent_id=parent_id,
        is_active=is_active,
        is_global=is_global,
        limit=limit,
        offset=offset,
    )
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> CategoryRead:
    return await catalog_service.create_category(session, payload, market_id)


@router.get("/categories/{category_id}", response_model=CategoryRead)
async def get_category(
    category_id: UUID,
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> CategoryRead:
    return await catalog_service.get_category(session, category_id, market_id)


@router.patch("/categories/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> CategoryRead:
    return await catalog_service.update_category(session, category_id, payload, market_id)


@router.delete("/categories/{category_id}", response_model=CategoryRead)
async def delete_category(
    category_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> CategoryRead:
    return await catalog_service.delete_category(session, category_id, market_id)


@router.get("/products", response_model=ListResponse[ProductRead])
async def list_products(
    search: str | None = None,
    brand_id: UUID | None = None,
    category_id: UUID | None = None,
    barcode: str | None = None,
    is_active: bool | None = None,
    is_global: bool | None = None,
    include_global: bool = True,
    has_image: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[ProductRead]:
    items, total = await catalog_service.list_products(
        session,
        market_id=market_id,
        include_global=include_global,
        search=search,
        brand_id=brand_id,
        category_id=category_id,
        barcode=barcode,
        is_active=is_active,
        is_global=is_global,
        has_image=has_image,
        limit=limit,
        offset=offset,
    )
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/products/global-search", response_model=ListResponse[ProductRead])
async def search_global_products(
    search: str | None = None,
    barcode: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    market_id: UUID = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[ProductRead]:
    items, total = await catalog_service.search_global_products(
        session,
        search=search,
        barcode=barcode,
        limit=limit,
        offset=offset,
    )
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> ProductRead:
    return await catalog_service.create_product(session, payload, market_id)


@router.post("/market-products/adopt", response_model=MarketProductRead, status_code=status.HTTP_201_CREATED)
async def adopt_global_product(
    payload: MarketProductAdoptCreate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> MarketProductRead:
    return await catalog_service.adopt_global_product(
        session,
        market_id=market_id,
        product_id=payload.product_id,
        regular_price=payload.regular_price,
        promo_price=payload.promo_price,
        currency=payload.currency,
        display_name_override=payload.display_name_override,
        category_override_id=payload.category_override_id,
        badge_text=payload.badge_text,
        stock_note=payload.stock_note,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )


@router.post("/market-products/private", response_model=MarketProductRead, status_code=status.HTTP_201_CREATED)
async def create_private_market_product(
    payload: PrivateMarketProductCreate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> MarketProductRead:
    return await catalog_service.create_private_market_product(
        session,
        market_id=market_id,
        private_name=payload.private_name,
        regular_price=payload.regular_price,
        promo_price=payload.promo_price,
        currency=payload.currency,
        display_name_override=payload.display_name_override,
        category_override_id=payload.category_override_id,
        badge_text=payload.badge_text,
        stock_note=payload.stock_note,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        private_brand_text=payload.private_brand_text,
        private_barcode=payload.private_barcode,
        private_sku=payload.private_sku,
        private_package_size=payload.private_package_size,
        private_package_type=payload.private_package_type,
    )


@router.post("/private-products", response_model=ResolvedMarketProductRead, status_code=status.HTTP_201_CREATED)
async def create_private_product_alias(payload: PrivateMarketProductCreate, market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)), session: AsyncSession = Depends(get_catalog_session)):
    row = await create_private_market_product(payload, market_id, session)
    return catalog_service.resolved_market_product(await catalog_service.get_market_product(session, row.id, market_id))


@router.get("/shared", response_model=ListResponse[SharedCatalogProductRead])
async def shared_catalog(search: str | None = None, barcode: str | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)):
    market = await session.get(Market, market_id)
    from app.services.entitlements import require_capability
    require_capability(market, "global_catalog_access")
    products, total = await catalog_service.search_global_products(session, search=search, barcode=barcode, limit=limit, offset=offset)
    adopted = set((await session.scalars(select(MarketProduct.product_id).where(MarketProduct.market_id == market_id, MarketProduct.product_id.is_not(None)))).all())
    items = [SharedCatalogProductRead(id=p.id, name=p.name, brand=p.brand.name if p.brand else None, package_size=p.package_size, package_type=p.package_type, barcode=p.barcode, category=p.category.name if p.category else None, image_url=(next((i.url for i in p.images if i.is_primary), None)), is_active=p.is_active, already_added=p.id in adopted) for p in products]
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/my-products", response_model=ListResponse[ResolvedMarketProductRead])
async def my_products(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0), market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)):
    rows = await catalog_service.list_my_market_products(session, market_id)
    items = [catalog_service.resolved_market_product(row) for row in rows]
    return ListResponse(items=items[offset:offset + limit], total=len(items), limit=limit, offset=offset)


@router.patch("/my-products/{market_product_id}", response_model=ResolvedMarketProductRead)
async def patch_my_product(market_product_id: UUID, payload: MarketProductUpdate, market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)), session: AsyncSession = Depends(get_catalog_session)):
    row = await catalog_service.update_market_product(session, market_product_id, market_id, payload)
    return catalog_service.resolved_market_product(await catalog_service.get_market_product(session, row.id, market_id))


@router.post("/shared/{product_id}/adopt", response_model=ResolvedMarketProductRead, status_code=status.HTTP_201_CREATED)
async def adopt_shared_product(product_id: UUID, payload: MarketProductAdoptCreate | None = None, market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)), session: AsyncSession = Depends(get_catalog_session)):
    data = payload or MarketProductAdoptCreate(product_id=product_id)
    row = await catalog_service.adopt_global_product(session, market_id=market_id, product_id=product_id, **data.model_dump(exclude={"product_id"}))
    return catalog_service.resolved_market_product(await catalog_service.get_market_product(session, row.id, market_id))


@router.post("/my-products/{market_product_id}/image", response_model=ResolvedMarketProductRead, status_code=status.HTTP_200_OK)
async def upload_market_image(market_product_id: UUID, request: Request, market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)), session: AsyncSession = Depends(get_catalog_session)):
    mime_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    row = await catalog_service.upload_market_product_image(session, market_product_id, market_id, await request.body(), mime_type)
    return catalog_service.resolved_market_product(row)


@router.delete("/my-products/{market_product_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_market_image(market_product_id: UUID, market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)), session: AsyncSession = Depends(get_catalog_session)):
    await catalog_service.remove_market_product_image(session, market_product_id, market_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/my-products/{market_product_id}/image/content", include_in_schema=False)
async def market_image_content(market_product_id: UUID, market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)):
    row = await catalog_service.get_market_product(session, market_product_id, market_id)
    if not row.image_storage_key:
        raise HTTPException(status_code=404, detail="Image not found.")
    path = catalog_service.storage_path_for_key(row.image_storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found.")
    return FileResponse(path, media_type=row.image_mime_type or "application/octet-stream")


@router.get("/products/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: UUID,
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> ProductRead:
    return await catalog_service.get_product(session, product_id, market_id)


@router.patch("/products/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> ProductRead:
    return await catalog_service.update_product(session, product_id, payload, market_id)


@router.delete("/products/{product_id}", response_model=ProductRead)
async def delete_product(
    product_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> ProductRead:
    return await catalog_service.delete_product(session, product_id, market_id)


@router.post(
    "/products/{product_id}/aliases",
    response_model=ProductAliasRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_alias(
    product_id: UUID,
    payload: ProductAliasCreate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> ProductAliasRead:
    return await catalog_service.create_product_alias(session, product_id, payload, market_id)


@router.delete("/products/{product_id}/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_alias(
    product_id: UUID,
    alias_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> Response:
    await catalog_service.delete_product_alias(session, product_id, alias_id, market_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
