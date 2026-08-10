"""Bulk-attach operator-supplied product images to a market's catalog.

Phase 31: the Phase 28A image resolver only ever assigns a *safe* image -
one already stored on a MarketProduct or global Product row with
quality_status in {good, excellent}. In production, a freshly onboarded
market's catalog frequently has no image data at all for common products
(e.g. "Coca Cola 1L"), so every campaign item falls back to the "no image"
placeholder - correctly, since assigning the wrong photo would be worse.

This script gives an operator a deterministic, scriptable way to populate
those images from files they already have (their own photography, a
supplier's licensed asset, etc.) - it does not fetch, scrape, or invent any
image content. It only wires existing catalog upload plumbing
(`catalog.create_private_market_product` / `catalog.upload_market_product_image`)
to a manifest instead of the admin UI, one row at a time.

Manifest format (JSON array):
[
  {"name": "Coca Cola 1L", "image_path": "assets/coca_cola_1l.jpg"},
  {"market_product_id": "3fa8...", "image_path": "assets/eti_burcak.jpg"}
]

`name` is matched against the market's existing catalog via the same
identity normalization the campaign resolver uses (Turkish-aware, unit and
punctuation-insensitive); if nothing matches, a new private market product
is created with that name so the image has somewhere to live. Pass
`market_product_id` directly to target an existing row unambiguously.

Usage:
    python -m scripts.import_market_product_images --market-id <uuid> --manifest catalog_images.json [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, engine
from app.services import catalog
from app.services.product_identity import normalize_product_identity

_FALLBACK_MIME = "application/octet-stream"


async def _match_market_product_id(session: AsyncSession, market_id: UUID, name: str) -> UUID | None:
    target = normalize_product_identity(name).normalized_full_name
    matches = [
        row.id
        for row in await catalog.list_my_market_products(session, market_id)
        if normalize_product_identity(catalog.resolve_effective_product(row.product, row).name).normalized_full_name == target
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"{len(matches)} existing catalog rows match {name!r}; pass market_product_id to disambiguate.")
    return None


async def _import_one(session: AsyncSession, market_id: UUID, entry: dict, *, dry_run: bool) -> dict:
    name = entry.get("name")
    image_path = Path(entry["image_path"])
    if not image_path.is_file():
        return {"name": name, "status": "error", "reason": f"image_path not found: {image_path}"}

    market_product_id_raw = entry.get("market_product_id")
    created_new = False
    if market_product_id_raw:
        market_product_id = UUID(str(market_product_id_raw))
    elif name:
        try:
            market_product_id = await _match_market_product_id(session, market_id, name)
        except ValueError as exc:
            return {"name": name, "status": "error", "reason": str(exc)}
        if market_product_id is None:
            if dry_run:
                return {"name": name, "status": "would_create_and_upload"}
            row = await catalog.create_private_market_product(session, market_id=market_id, private_name=name)
            market_product_id = row.id
            created_new = True
    else:
        return {"name": name, "status": "error", "reason": "entry needs 'name' or 'market_product_id'"}

    if dry_run:
        return {"name": name, "market_product_id": str(market_product_id), "status": "would_upload"}

    mime_type = mimetypes.guess_type(image_path.name)[0] or _FALLBACK_MIME
    content = image_path.read_bytes()
    await catalog.upload_market_product_image(session, market_product_id, market_id, content, mime_type)
    return {
        "name": name,
        "market_product_id": str(market_product_id),
        "status": "created_and_uploaded" if created_new else "uploaded",
    }


async def import_market_product_images(market_id: UUID, manifest: list[dict], *, dry_run: bool = False) -> dict:
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is required to import catalog images.")
    results: list[dict] = []
    async with AsyncSessionLocal() as session:
        for entry in manifest:
            try:
                results.append(await _import_one(session, market_id, entry, dry_run=dry_run))
            except Exception as exc:  # noqa: BLE001 - one bad row must not abort the batch
                results.append({"name": entry.get("name"), "status": "error", "reason": str(exc)})
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {"market_id": str(market_id), "dry_run": dry_run, "counts": counts, "results": results}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market-id", required=True, type=UUID)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to a JSON manifest (see module docstring).")
    parser.add_argument("--dry-run", action="store_true", help="Resolve matches without uploading anything.")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise SystemExit("Manifest must be a JSON array of {name|market_product_id, image_path} objects.")

    try:
        summary = await import_market_product_images(args.market_id, manifest, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2, sort_keys=True))
    finally:
        if engine is not None:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
