"""Platform-admin catalog quality API routes."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_platform_admin
from app.models import PlatformAdmin
from app.schemas.platform_catalog import (
    PlatformCatalogMerge,
    PlatformCatalogMergePreview,
    PlatformCatalogQualityIgnore,
)
from app.services.catalog_quality import (
    ignore_catalog_quality_candidate,
    merge_global_products,
    preview_global_product_merge,
    scan_catalog_quality_candidates,
)

router = APIRouter(prefix="/platform/catalog/quality", tags=["platform-catalog-quality"])
admin = Depends(get_current_platform_admin)


@router.get("/candidates", response_model=dict)
async def list_catalog_quality_candidates(
    state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: PlatformAdmin = admin,
    session: AsyncSession = Depends(get_catalog_session),
) -> dict:
    return await scan_catalog_quality_candidates(
        session,
        state_name=state,
        limit=limit,
        offset=offset,
    )


@router.post("/ignore", response_model=dict)
async def ignore_catalog_quality_pair(
    payload: PlatformCatalogQualityIgnore,
    current_admin: PlatformAdmin = admin,
    session: AsyncSession = Depends(get_catalog_session),
) -> dict:
    return await ignore_catalog_quality_candidate(
        session,
        actor=current_admin,
        product_a_id=payload.product_a_id,
        product_b_id=payload.product_b_id,
        note=payload.note,
    )


@router.post("/merge-preview", response_model=dict)
async def catalog_product_merge_preview(
    payload: PlatformCatalogMergePreview,
    _: PlatformAdmin = admin,
    session: AsyncSession = Depends(get_catalog_session),
) -> dict:
    return await preview_global_product_merge(
        session,
        source_product_id=payload.source_product_id,
        target_product_id=payload.target_product_id,
    )


@router.post("/merge", response_model=dict)
async def merge_catalog_products(
    payload: PlatformCatalogMerge,
    current_admin: PlatformAdmin = admin,
    session: AsyncSession = Depends(get_catalog_session),
) -> dict:
    return await merge_global_products(
        session,
        actor=current_admin,
        source_product_id=payload.source_product_id,
        target_product_id=payload.target_product_id,
        confirm_barcode_mismatch=payload.confirm_barcode_mismatch,
    )
