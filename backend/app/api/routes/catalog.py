from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_market_id, require_market_role
from app.core.roles import MARKET_MUTATION_ROLES
from app.schemas.brand import BrandCreate, BrandRead, BrandUpdate
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.common import ListResponse
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


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_catalog_session),
) -> ProductRead:
    return await catalog_service.create_product(session, payload, market_id)


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
