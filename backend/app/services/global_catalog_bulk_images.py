"""Bulk ZIP/manifest matching and import for platform-admin global product images.

Matching priority is product_id, then barcode, then normalized (Turkish-aware)
name -- the same priority the resolver's own catalog matching favors. A row is
only ever attached automatically when it resolves to exactly one global
product; anything else is surfaced to the admin instead of guessed at.
"""

from __future__ import annotations

import base64
import csv
import io
import zipfile
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import HTTPException, Request
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Product, ProductImage
from app.services.image_pipeline import (
    MAX_UPLOAD_BYTES,
    normalize_flyer_image,
    require_supported_image_mime_type,
    store_flyer_image,
)
from app.services.product_identity import normalize_product_text

MAX_ZIP_BYTES = 60 * 1024 * 1024
MAX_ZIP_ENTRIES = 600
MAX_MANIFEST_ROWS = 500
THUMBNAIL_EDGE = 96

EXTENSION_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class BulkImportError(ValueError):
    """Structural problem with the uploaded ZIP package itself."""


async def read_bounded_zip_body(request: Request, max_bytes: int = MAX_ZIP_BYTES) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status_code=413, detail="ZIP package exceeds the upload size limit.")
        chunks.append(chunk)
    return b"".join(chunks)


@dataclass
class BulkImageRow:
    row_index: int
    name: str | None
    barcode: str | None
    sku: str | None
    product_id_hint: str | None
    image_filename: str | None
    status: str = "invalid"  # exact_match | matched | ambiguous | unmatched | invalid | error
    match_method: str | None = None
    matched_product: dict | None = None
    candidates: list[dict] = field(default_factory=list)
    reason: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    thumbnail_data_uri: str | None = None

    def to_dict(self) -> dict:
        return {
            "row_index": self.row_index,
            "name": self.name,
            "barcode": self.barcode,
            "sku": self.sku,
            "product_id_hint": self.product_id_hint,
            "image_filename": self.image_filename,
            "status": self.status,
            "match_method": self.match_method,
            "matched_product": self.matched_product,
            "candidates": self.candidates,
            "reason": self.reason,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "thumbnail_data_uri": self.thumbnail_data_uri,
        }


@dataclass
class BulkZipContents:
    manifest_rows: list[dict]
    images: dict[str, bytes]


def extract_zip(content: bytes) -> BulkZipContents:
    if not content:
        raise BulkImportError("ZIP package is empty.")
    if len(content) > MAX_ZIP_BYTES:
        raise BulkImportError("ZIP package must be 60 MiB or smaller.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise BulkImportError("File is not a valid ZIP package.") from None

    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise BulkImportError("ZIP package contains too many entries.")

    manifest_bytes: bytes | None = None
    images: dict[str, bytes] = {}
    total_uncompressed = 0
    for info in infos:
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            raise BulkImportError("ZIP package contains unsafe file paths.")
        if info.file_size > MAX_UPLOAD_BYTES:
            raise BulkImportError(f"'{name}' exceeds the per-file size limit.")
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_ZIP_BYTES:
            raise BulkImportError("ZIP package is too large once decompressed.")
        data = archive.read(info)
        base_name = name.rsplit("/", 1)[-1]
        if name.lower() == "manifest.csv":
            manifest_bytes = data
        elif name.startswith("images/") and base_name:
            images[base_name] = data

    if manifest_bytes is None:
        raise BulkImportError("ZIP package must contain manifest.csv.")

    rows = _parse_manifest_csv(manifest_bytes)
    if len(rows) > MAX_MANIFEST_ROWS:
        raise BulkImportError("manifest.csv contains too many rows.")
    return BulkZipContents(manifest_rows=rows, images=images)


def _parse_manifest_csv(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise BulkImportError("manifest.csv has no header row.")
    fields = {name: (name or "").strip().lower() for name in reader.fieldnames}
    return [{fields[key]: (value or "").strip() for key, value in raw.items() if key in fields} for raw in reader]


def _extension_of(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot >= 0 else ""


def _product_brief(product: Product) -> dict:
    return {"id": str(product.id), "name": product.name, "barcode": product.barcode}


def _thumbnail_data_uri(content: bytes) -> str | None:
    try:
        with Image.open(io.BytesIO(content)) as source:
            image = source.convert("RGBA") if source.mode in {"RGBA", "LA", "P"} else source.convert("RGB")
            image.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE))
            buffer = io.BytesIO()
            if image.mode == "RGBA":
                image.save(buffer, format="PNG")
                out_mime = "image/png"
            else:
                image.save(buffer, format="JPEG", quality=70)
                out_mime = "image/jpeg"
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:{out_mime};base64,{encoded}"
    except Exception:
        return None


async def match_bulk_rows(session: AsyncSession, manifest_rows: list[dict], images: dict[str, bytes]) -> list[BulkImageRow]:
    products = list(
        (await session.scalars(select(Product).options(selectinload(Product.aliases)).where(Product.is_global.is_(True)))).all()
    )
    by_id = {str(product.id): product for product in products}
    by_barcode: dict[str, list[Product]] = {}
    by_name: dict[str, list[Product]] = {}
    for product in products:
        if product.barcode:
            by_barcode.setdefault(product.barcode.strip(), []).append(product)
        by_name.setdefault(normalize_product_text(product.name), []).append(product)
        for alias in product.aliases:
            by_name.setdefault(alias.normalized_alias, []).append(product)

    results: list[BulkImageRow] = []
    for index, raw in enumerate(manifest_rows):
        row = BulkImageRow(
            row_index=index + 2,
            name=raw.get("name") or None,
            barcode=raw.get("barcode") or None,
            sku=raw.get("sku") or None,
            product_id_hint=raw.get("product_id") or None,
            image_filename=raw.get("image_filename") or None,
        )
        if not row.image_filename:
            row.reason = "image_filename is required."
            results.append(row)
            continue
        if row.image_filename not in images:
            row.reason = f"'{row.image_filename}' was not found under images/."
            results.append(row)
            continue
        extension = _extension_of(row.image_filename)
        if extension not in EXTENSION_MIME:
            row.reason = "Unsupported image file extension."
            results.append(row)
            continue
        if not (row.product_id_hint or row.barcode or row.sku or row.name):
            row.reason = "Row has no product identifier (product_id, barcode, sku, or name)."
            results.append(row)
            continue

        content = images[row.image_filename]
        declared_mime = EXTENSION_MIME[extension]
        try:
            normalized = normalize_flyer_image(content, declared_mime)
        except HTTPException as exc:
            row.reason = str(exc.detail)
            results.append(row)
            continue
        except Exception as exc:
            row.status = "error"
            row.reason = str(exc) or "Unexpected error validating image."
            results.append(row)
            continue

        row.mime_type = declared_mime
        row.width = normalized.width
        row.height = normalized.height
        row.thumbnail_data_uri = _thumbnail_data_uri(content)

        try:
            _match_row(row, by_id, by_barcode, by_name)
        except Exception as exc:
            row.status = "error"
            row.reason = str(exc) or "Unexpected error while matching this row."
        results.append(row)
    return results


def _match_row(row: BulkImageRow, by_id: dict, by_barcode: dict, by_name: dict) -> None:
    if row.product_id_hint:
        product = by_id.get(row.product_id_hint.strip())
        if product is not None:
            row.status, row.match_method, row.matched_product = "exact_match", "product_id", _product_brief(product)
            return
        row.status, row.reason = "unmatched", "No global product matches the given product_id."
        return

    if row.barcode:
        candidates = by_barcode.get(row.barcode.strip(), [])
        if len(candidates) == 1:
            row.status, row.match_method, row.matched_product = "exact_match", "barcode", _product_brief(candidates[0])
            return
        if len(candidates) > 1:
            row.status, row.match_method = "ambiguous", "barcode"
            row.candidates = [_product_brief(product) for product in candidates]
            row.reason = "Multiple global products share this barcode."
            return

    if row.name:
        candidates = list({product.id: product for product in by_name.get(normalize_product_text(row.name), [])}.values())
        if len(candidates) == 1:
            row.status, row.match_method, row.matched_product = "matched", "name", _product_brief(candidates[0])
            return
        if len(candidates) > 1:
            row.status, row.match_method = "ambiguous", "name"
            row.candidates = [_product_brief(product) for product in candidates]
            row.reason = "Multiple global products match this name."
            return

    row.status, row.reason = "unmatched", "No global product matched this row."


@dataclass
class BulkImportSummary:
    total: int = 0
    matched: int = 0
    uploaded: int = 0
    needs_review: int = 0
    approved: int = 0
    rejected: int = 0
    ambiguous: int = 0
    unmatched: int = 0
    invalid: int = 0
    errors: int = 0
    rows: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "matched": self.matched,
            "uploaded": self.uploaded,
            "needs_review": self.needs_review,
            "approved": self.approved,
            "rejected": self.rejected,
            "ambiguous": self.ambiguous,
            "unmatched": self.unmatched,
            "invalid": self.invalid,
            "errors": self.errors,
            "rows": self.rows,
        }


async def import_bulk_rows(
    session: AsyncSession,
    rows: list[BulkImageRow],
    images: dict[str, bytes],
    resolutions: dict[int, UUID],
) -> BulkImportSummary:
    summary = BulkImportSummary(total=len(rows))
    for row in rows:
        if row.status in {"exact_match", "matched"}:
            summary.matched += 1
        elif row.status == "ambiguous":
            summary.ambiguous += 1
        elif row.status == "unmatched":
            summary.unmatched += 1
        elif row.status == "invalid":
            summary.invalid += 1
        elif row.status == "error":
            summary.errors += 1

    for row in rows:
        entry = {"row_index": row.row_index, "image_filename": row.image_filename, "status": row.status, "match_method": row.match_method}
        target_product_id: UUID | None = None
        if row.status in {"exact_match", "matched"} and row.matched_product:
            target_product_id = UUID(row.matched_product["id"])
        elif row.status == "ambiguous":
            resolved = resolutions.get(row.row_index)
            if resolved is not None and any(str(resolved) == candidate["id"] for candidate in row.candidates):
                target_product_id = resolved
            else:
                entry["reason"] = "Skipped: ambiguous row was not resolved to one of its candidates."
                summary.rows.append(entry)
                continue
        else:
            entry["reason"] = row.reason
            summary.rows.append(entry)
            continue

        product = await session.scalar(select(Product).where(Product.id == target_product_id, Product.is_global.is_(True)))
        if product is None:
            entry["status"], entry["reason"] = "error", "Matched product is no longer a valid global product."
            summary.errors += 1
            summary.rows.append(entry)
            continue

        try:
            mime_type = require_supported_image_mime_type(row.mime_type or "")
            asset = store_flyer_image(namespace=f"global/catalog/{product.id}", original_content=images[row.image_filename], declared_mime_type=mime_type)
        except HTTPException as exc:
            entry["status"], entry["reason"] = "error", str(exc.detail)
            summary.errors += 1
            summary.rows.append(entry)
            continue

        image = ProductImage(
            product_id=product.id,
            storage_key=asset.storage_key,
            mime_type=asset.mime_type,
            size_bytes=asset.size_bytes,
            width=asset.width,
            height=asset.height,
            has_transparent_background=asset.has_alpha,
            quality_status="needs_review",
            is_primary=False,
        )
        session.add(image)
        await session.flush()
        summary.uploaded += 1
        summary.needs_review += 1
        entry["product_id"] = str(product.id)
        entry["image_id"] = str(image.id)
        summary.rows.append(entry)

    await session.commit()
    return summary
