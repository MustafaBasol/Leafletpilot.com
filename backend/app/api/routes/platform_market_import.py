from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_platform_admin
from app.models import PlatformAdmin
from app.schemas.market_catalog_import import MarketCatalogImportCommitRequest
from app.services.market_catalog_excel import build_template
from app.services.market_catalog_import import commit_import, preview_import

router = APIRouter(prefix="/platform/markets", tags=["platform-market-catalog-import"])
admin = Depends(get_current_platform_admin)


@router.get("/{market_id}/catalog-import/template", response_class=Response)
async def download_market_import_template(market_id: UUID, _: PlatformAdmin = admin):
    return Response(
        content=build_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="leafletpilot-market-products-template.xlsx"'},
    )


async def _read_workbook(request: Request) -> tuple[bytes, str | None]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type == "multipart/form-data":
        form = await request.form()
        workbook = form.get("workbook")
        if workbook is None or not hasattr(workbook, "read"):
            raise HTTPException(422, "workbook alanı zorunludur.")
        content = await workbook.read()
        filename = getattr(workbook, "filename", None)
    elif content_type in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    }:
        content, filename = await request.body(), None
    else:
        raise HTTPException(415, "Yalnızca .xlsx formu kabul edilir.")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Excel dosyası en fazla 10 MiB olabilir.")
    return content, filename


@router.post("/{market_id}/catalog-import/preview", response_model=dict)
async def preview_market_catalog_import(
    market_id: UUID,
    request: Request,
    admin: PlatformAdmin = admin,
    session: AsyncSession = Depends(get_catalog_session),
):
    content, filename = await _read_workbook(request)
    return await preview_import(session, market_id=market_id, admin=admin, filename=filename or "upload.xlsx", content=content)


@router.post("/{market_id}/catalog-import/{import_id}/commit", response_model=dict)
async def commit_market_catalog_import(
    market_id: UUID,
    import_id: UUID,
    payload: MarketCatalogImportCommitRequest,
    admin: PlatformAdmin = admin,
    session: AsyncSession = Depends(get_catalog_session),
):
    try:
        decisions = {int(row_number): decision for row_number, decision in payload.decisions.items()}
    except ValueError:
        raise HTTPException(422, "decisions anahtarları satır numarası olmalıdır.") from None
    return await commit_import(session, market_id=market_id, admin=admin, import_id=import_id, decisions=decisions)
