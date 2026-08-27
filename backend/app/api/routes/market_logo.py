from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_market_id, require_market_role
from app.core.roles import MarketRole
from app.models import Market
from app.services.image_pipeline import read_bounded_image_body, require_supported_image_mime_type, store_flyer_image
from app.services.rendering import storage_path_for_key

router = APIRouter(prefix="/market", tags=["market"])


async def _market(session: AsyncSession, market_id: UUID, *, lock: bool = False) -> Market:
    query = select(Market).where(Market.id == market_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Market not found.")
    return row


@router.get("/logo")
async def get_logo(market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)) -> dict:
    row = await _market(session, market_id)
    return {"has_logo": bool(row.logo_storage_key), "mime_type": row.logo_mime_type}


@router.get("/logo/content", include_in_schema=False)
async def get_logo_content(market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)):
    row = await _market(session, market_id)
    if not row.logo_storage_key:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Market logo not found.")
    path = storage_path_for_key(row.logo_storage_key)
    if not path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Market logo file not found.")
    return FileResponse(path, media_type=row.logo_mime_type or "application/octet-stream", headers={"Cache-Control": "no-store"})


@router.put("/logo")
async def upload_logo(request: Request, market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)), session: AsyncSession = Depends(get_catalog_session)) -> dict:
    mime_type = require_supported_image_mime_type(request.headers.get("content-type", ""))
    content = await read_bounded_image_body(request)
    asset = store_flyer_image(namespace=f"markets/{market_id}/logo", original_content=content, declared_mime_type=mime_type)
    row = await _market(session, market_id, lock=True)
    row.logo_storage_key = asset.storage_key
    row.logo_mime_type = asset.mime_type
    row.logo_url = None
    await session.commit()
    return {"has_logo": True, "mime_type": row.logo_mime_type}


@router.delete("/logo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_logo(market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)), session: AsyncSession = Depends(get_catalog_session)) -> Response:
    row = await _market(session, market_id, lock=True)
    row.logo_storage_key = row.logo_mime_type = row.logo_url = None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)