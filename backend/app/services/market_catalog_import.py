"""Phase 28D — Platform-admin controlled market catalog import.

Preview-then-commit workflow for importing one market's product spreadsheet.
The spreadsheet only ever *proposes* rows; every write funnels through the
existing Phase 28B/28C authoritative catalog services (``app.services.catalog``)
so duplicate guards, brand/category resolution, plan entitlements, and merge
tombstone handling are never bypassed or re-implemented here.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ActivityLog,
    Category,
    Market,
    MarketCatalogImport,
    MarketProduct,
    PlatformAdmin,
    PlatformAuditLog,
    Product,
)
from app.models.base import utc_now
from app.schemas.market_catalog_import import ImportRowDecision
from app.schemas.market_product import MarketProductUpdate
from app.services import catalog
from app.services.catalog_matching import (
    CatalogMatchCandidate,
    CatalogMatchResult,
    canonical_name_key,
    canonical_package_key,
    eligible_global_product_conditions,
    match_global_products,
)
from app.services.entitlements import resolve_capabilities
from app.services.market_catalog_excel import parse_workbook
from app.services.product_identity import normalize_barcode, normalize_words
from app.services.product_normalization import (
    normalize_currency,
    normalize_package_type,
    normalize_package_unit,
    parse_package,
)

PREVIEW_TTL = timedelta(minutes=30)
ROW_STATES = (
    "global_exact_match",
    "global_strong_match",
    "global_ambiguous",
    "existing_market_product",
    "new_market_local",
    "invalid",
    "duplicate_in_file",
    "conflict",
)
_BLOCKING_STATES = {"invalid", "conflict"}


def _not_found(label: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found.")


# --------------------------------------------------------------------------
# Row normalization
# --------------------------------------------------------------------------


# MarketProduct.regular_price/promo_price are Numeric(10, 2) columns; a value
# outside this range would otherwise reach Postgres as an unhandled overflow
# error during commit instead of a clean preview-time validation error.
_MAX_PRICE = Decimal("99999999.99")


def _parse_decimal(raw: str, *, field: str) -> Decimal:
    text = raw.strip().replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{field}: geçersiz sayı '{raw}'.") from None
    if value < 0:
        raise ValueError(f"{field}: negatif olamaz.")
    if value > _MAX_PRICE:
        raise ValueError(f"{field}: {_MAX_PRICE} değerinden büyük olamaz.")
    return value


def _normalize_row(raw: dict[str, Any], *, market_currency: str) -> tuple[dict, dict, list[str]]:
    errors: list[str] = []
    original = {
        column: str(raw.get(column, "")).strip()
        for column in (
            "product_name", "brand", "barcode", "package_amount", "package_unit",
            "package_type", "package_size", "category", "price", "promo_price",
            "currency", "sku", "image_url",
        )
        if str(raw.get(column, "")).strip()
    }

    name = original.get("product_name", "")
    if not name:
        errors.append("product_name zorunludur.")

    image_url = original.get("image_url")
    if image_url and urlparse(image_url).scheme not in {"http", "https"}:
        errors.append("image_url http veya https ile başlamalıdır.")
        image_url = None

    package_size = original.get("package_size")
    raw_amount = original.get("package_amount")
    raw_unit = original.get("package_unit")
    package_amount: Decimal | None = None
    package_unit: str | None = None
    if raw_amount or raw_unit:
        if raw_amount:
            try:
                package_amount = _parse_decimal(raw_amount, field="package_amount")
            except ValueError as exc:
                errors.append(str(exc))
        if raw_unit:
            package_unit = normalize_package_unit(raw_unit)
            if package_unit is None:
                errors.append(f"package_unit tanınmıyor: '{raw_unit}'.")
        if (package_amount is None) != (package_unit is None):
            errors.append("package_amount ve package_unit birlikte verilmelidir.")
    elif package_size:
        package_amount, package_unit = parse_package(package_size)

    package_type_raw = original.get("package_type")
    package_type = normalize_package_type(package_type_raw) if package_type_raw else None
    if package_type_raw and package_type is None:
        errors.append(f"package_type tanınmıyor: '{package_type_raw}'.")

    price: Decimal | None = None
    if original.get("price"):
        try:
            price = _parse_decimal(original["price"], field="price")
        except ValueError as exc:
            errors.append(str(exc))
    promo_price: Decimal | None = None
    if original.get("promo_price"):
        try:
            promo_price = _parse_decimal(original["promo_price"], field="promo_price")
        except ValueError as exc:
            errors.append(str(exc))

    currency = market_currency
    if original.get("currency"):
        try:
            currency = normalize_currency(original["currency"], strict=True)
        except ValueError:
            errors.append(f"Desteklenmeyen para birimi: '{original['currency']}'.")

    normalized = {
        "product_name": name,
        "brand": original.get("brand"),
        "barcode": original.get("barcode"),
        "sku": original.get("sku"),
        "category": original.get("category"),
        "package_size": package_size,
        "package_amount": str(package_amount) if package_amount is not None else None,
        "package_unit": package_unit,
        "package_type": package_type,
        "price": str(price) if price is not None else None,
        "promo_price": str(promo_price) if promo_price is not None else None,
        "currency": currency,
        "image_url": image_url,
    }
    return original, normalized, errors


def _dedup_key(normalized: dict) -> tuple:
    barcode = normalize_barcode(normalized.get("barcode"))
    if barcode:
        return ("barcode", barcode)
    package_amount = Decimal(normalized["package_amount"]) if normalized.get("package_amount") else None
    package_key = canonical_package_key(
        amount=package_amount,
        unit=normalized.get("package_unit"),
        package_size=normalized.get("package_size"),
        fallback_name=normalized["product_name"],
    )
    return (
        "identity",
        canonical_name_key(normalized["product_name"], normalized.get("brand")),
        normalize_words(normalized.get("brand")),
        package_key or "",
    )


def _apply_dedup(drafts: list[dict]) -> None:
    groups: dict[tuple, list[dict]] = {}
    for draft in drafts:
        if not draft.get("_pending"):
            continue
        groups.setdefault(_dedup_key(draft["normalized"]), []).append(draft)
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda d: d["row"])
        first = group[0]
        signatures = {
            (d["normalized"].get("price"), d["normalized"].get("promo_price"), d["normalized"].get("currency"))
            for d in group
        }
        if len(signatures) == 1:
            for dup in group[1:]:
                dup.pop("_pending", None)
                dup.update(
                    state="duplicate_in_file",
                    proposed_action="skip",
                    global_match=None,
                    existing_market_product_id=None,
                    duplicate_of_row=first["row"],
                    warnings=[],
                    errors=[f"Satır {first['row']} ile aynı ürün; bu satır atlanacak."],
                )
        else:
            rows_text = ", ".join(str(d["row"]) for d in group)
            for dup in group:
                dup.pop("_pending", None)
                dup.update(
                    state="conflict",
                    proposed_action="blocked",
                    global_match=None,
                    existing_market_product_id=None,
                    duplicate_of_row=first["row"] if dup is not first else None,
                    warnings=[],
                    errors=[f"Dosyada aynı ürün için çelişen değerler var (satırlar: {rows_text})."],
                )


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


def _build_local_indexes(
    local_rows: list[MarketProduct],
) -> tuple[dict[str, str], dict[str, str], dict[tuple, str]]:
    barcode_index: dict[str, str] = {}
    sku_index: dict[str, str] = {}
    identity_index: dict[tuple, str] = {}
    for row in local_rows:
        name = row.display_name_override or row.private_name or ""
        if not name:
            continue
        identity_key = (
            canonical_name_key(name, row.private_brand_text),
            normalize_words(row.private_brand_text),
            canonical_package_key(
                amount=row.package_amount,
                unit=row.package_unit,
                package_size=row.private_package_size,
                fallback_name=name,
            )
            or "",
        )
        identity_index.setdefault(identity_key, str(row.id))
        barcode = normalize_barcode(row.private_barcode)
        if barcode:
            barcode_index.setdefault(barcode, str(row.id))
        if row.private_sku and row.private_sku.strip():
            sku_index.setdefault(row.private_sku.strip().casefold(), str(row.id))
    return barcode_index, sku_index, identity_index


async def _resolve_merged_barcode(
    session: AsyncSession, *, market_id: UUID, barcode: str
) -> CatalogMatchResult | None:
    """Redirect a barcode that only exists on a merged-away tombstone to its winner."""
    normalized_barcode = normalize_barcode(barcode)
    if not normalized_barcode:
        return None
    tombstone = await session.scalar(
        select(Product)
        .where(
            Product.is_global.is_(True),
            Product.market_id.is_(None),
            Product.merged_into_product_id.is_not(None),
            or_(Product.barcode == barcode.strip(), Product.barcode == normalized_barcode),
        )
        .order_by(Product.updated_at.desc())
        .limit(1)
    )
    if tombstone is None or tombstone.merged_into_product_id is None:
        return None
    winner = await session.scalar(
        select(Product)
        .options(selectinload(Product.brand), selectinload(Product.images))
        .where(Product.id == tombstone.merged_into_product_id, *eligible_global_product_conditions())
    )
    if winner is None:
        return None
    adopted = await session.scalar(
        select(MarketProduct.id).where(
            MarketProduct.market_id == market_id, MarketProduct.product_id == winner.id
        )
    )
    candidate = CatalogMatchCandidate(
        product=winner,
        match_type="strong",
        match_reason="resolved from merged product",
        already_adopted=adopted is not None,
    )
    return CatalogMatchResult("strong", "resolved from merged product", (candidate,), 1)


def _match_as_json(match: CatalogMatchResult | None) -> dict | None:
    if match is None:
        return None
    data = match.as_dict()
    for candidate in data["candidates"]:
        candidate["product_id"] = str(candidate["product_id"])
        if candidate.get("package_amount") is not None:
            candidate["package_amount"] = str(candidate["package_amount"])
    return data


async def _classify_row(
    session: AsyncSession,
    *,
    market_id: UUID,
    normalized: dict,
    adopted_by_product_id: dict[UUID, UUID],
    local_barcode_index: dict[str, str],
    local_sku_index: dict[str, str],
    local_identity_index: dict[tuple, str],
    global_categories: dict[str, Category],
    market_categories: dict[str, Category],
) -> dict:
    warnings: list[str] = []
    package_amount = Decimal(normalized["package_amount"]) if normalized.get("package_amount") else None

    barcode_key = normalize_barcode(normalized.get("barcode"))
    sku_key = normalized["sku"].strip().casefold() if normalized.get("sku") else None
    local_identity_key = (
        canonical_name_key(normalized["product_name"], normalized.get("brand")),
        normalize_words(normalized.get("brand")),
        canonical_package_key(
            amount=package_amount,
            unit=normalized.get("package_unit"),
            package_size=normalized.get("package_size"),
            fallback_name=normalized["product_name"],
        )
        or "",
    )
    existing_local_id = None
    if barcode_key and barcode_key in local_barcode_index:
        existing_local_id = local_barcode_index[barcode_key]
    elif sku_key and sku_key in local_sku_index:
        existing_local_id = local_sku_index[sku_key]
    elif local_identity_key in local_identity_index:
        existing_local_id = local_identity_index[local_identity_key]

    match = await match_global_products(
        session,
        market_id=market_id,
        name=normalized["product_name"],
        barcode=normalized.get("barcode"),
        brand=normalized.get("brand"),
        package_size=normalized.get("package_size"),
        package_type=normalized.get("package_type"),
        package_amount=package_amount,
        package_unit=normalized.get("package_unit"),
        package_type_canonical=normalized.get("package_type"),
    )
    if match.match_type == "none" and normalized.get("barcode"):
        redirected = await _resolve_merged_barcode(session, market_id=market_id, barcode=normalized["barcode"])
        if redirected is not None:
            match = redirected

    category_id = None
    if normalized.get("category"):
        key = normalized["category"].strip().casefold()
        category = global_categories.get(key) or market_categories.get(key)
        if category is not None:
            category_id = str(category.id)
        else:
            warnings.append(f"Kategori bulunamadı: '{normalized['category']}'. Ürün kategorisiz eklenecek.")

    already_adopted = [candidate for candidate in match.candidates if candidate.already_adopted]

    def finalize(state: str, action: str, existing_id: str | None, extra_warnings: list[str] | None = None) -> dict:
        return {
            "normalized": {**normalized, "category_id": category_id},
            "state": state,
            "proposed_action": action,
            "global_match": _match_as_json(match if match.match_type != "none" else None),
            "existing_market_product_id": existing_id,
            "duplicate_of_row": None,
            "warnings": warnings + (extra_warnings or []),
            "errors": [],
        }

    if len(already_adopted) == 1 and match.match_type != "ambiguous":
        product_id = already_adopted[0].product.id
        return finalize("existing_market_product", "update_existing", str(adopted_by_product_id.get(product_id)))
    if len(already_adopted) > 1:
        return finalize("conflict", "blocked", None, ["Birden fazla eşleşen global ürün bu markette zaten kullanılıyor."])
    if existing_local_id is not None:
        note = ["Bu ürün için global bir eşleşme de bulundu; mevcut yerel ürün güncellenecek."] if match.match_type != "none" else None
        return finalize("existing_market_product", "update_existing", existing_local_id, note)
    if match.match_type == "exact":
        return finalize("global_exact_match", "adopt_global", None)
    if match.match_type == "strong" and match.candidate_count == 1:
        return finalize("global_strong_match", "adopt_global", None)
    if match.match_type == "ambiguous":
        return finalize("global_ambiguous", "blocked", None)
    return finalize("new_market_local", "create_local", None)


def _row_counts(rows: list[dict]) -> dict:
    counts = {state: 0 for state in ROW_STATES}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    counts["total"] = len(rows)
    return counts


# --------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------


async def preview_import(
    session: AsyncSession,
    *,
    market_id: UUID,
    admin: PlatformAdmin,
    filename: str,
    content: bytes,
) -> dict:
    market = await session.get(Market, market_id)
    if market is None:
        raise _not_found("Market")

    raw_rows = parse_workbook(content)
    drafts: list[dict] = []
    for raw in raw_rows:
        row_number = raw["row"]
        if raw.get("status") == "invalid":
            drafts.append(
                {
                    "row": row_number, "original": {}, "normalized": {}, "state": "invalid",
                    "proposed_action": "blocked", "global_match": None,
                    "existing_market_product_id": None, "duplicate_of_row": None,
                    "warnings": [], "errors": [raw.get("error", "Geçersiz satır.")],
                }
            )
            continue
        original, normalized, errors = _normalize_row(raw, market_currency=market.currency)
        if errors:
            drafts.append(
                {
                    "row": row_number, "original": original, "normalized": normalized, "state": "invalid",
                    "proposed_action": "blocked", "global_match": None,
                    "existing_market_product_id": None, "duplicate_of_row": None,
                    "warnings": [], "errors": errors,
                }
            )
            continue
        drafts.append({"row": row_number, "original": original, "normalized": normalized, "_pending": True})

    _apply_dedup(drafts)

    adopted_pairs = (
        await session.execute(
            select(MarketProduct.product_id, MarketProduct.id).where(
                MarketProduct.market_id == market_id, MarketProduct.product_id.is_not(None)
            )
        )
    ).all()
    adopted_by_product_id = {product_id: mp_id for product_id, mp_id in adopted_pairs}
    local_rows = list(
        (
            await session.scalars(
                select(MarketProduct).where(
                    MarketProduct.market_id == market_id, MarketProduct.product_id.is_(None)
                )
            )
        ).all()
    )
    local_barcode_index, local_sku_index, local_identity_index = _build_local_indexes(local_rows)
    global_categories = {
        category.name.strip().casefold(): category
        for category in (
            await session.scalars(select(Category).where(Category.is_global.is_(True), Category.is_active.is_(True)))
        ).all()
    }
    market_categories = {
        category.name.strip().casefold(): category
        for category in (
            await session.scalars(
                select(Category).where(
                    Category.market_id == market_id, Category.is_global.is_(False), Category.is_active.is_(True)
                )
            )
        ).all()
    }

    rows: list[dict] = []
    for draft in drafts:
        if not draft.pop("_pending", False):
            rows.append(draft)
            continue
        classification = await _classify_row(
            session,
            market_id=market_id,
            normalized=draft["normalized"],
            adopted_by_product_id=adopted_by_product_id,
            local_barcode_index=local_barcode_index,
            local_sku_index=local_sku_index,
            local_identity_index=local_identity_index,
            global_categories=global_categories,
            market_categories=market_categories,
        )
        rows.append({**draft, **classification})
    rows.sort(key=lambda row: row["row"])

    capabilities = resolve_capabilities(market)
    current_local_count = len(local_rows)
    projected_new_local = sum(1 for row in rows if row["proposed_action"] == "create_local")
    limit = capabilities.private_products_limit
    quota = {
        "current_local_count": current_local_count,
        "projected_new_local": projected_new_local,
        "limit": limit,
        "would_exceed": limit is not None and (current_local_count + projected_new_local) > limit,
    }

    now = utc_now()
    job = MarketCatalogImport(
        market_id=market_id,
        uploaded_by_platform_admin_id=admin.id,
        original_filename=(filename or "upload.xlsx")[:255],
        status="previewed",
        total_rows=len(rows),
        preview_payload=rows,
        created_at=now,
        expires_at=now + PREVIEW_TTL,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return {
        "import_id": str(job.id),
        "market_id": str(market_id),
        "status": job.status,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
        "rows": rows,
        "counts": _row_counts(rows),
        "quota": quota,
    }


# --------------------------------------------------------------------------
# Commit
# --------------------------------------------------------------------------


def _default_action(row: dict) -> str:
    return {
        "global_exact_match": "adopt_global",
        "global_strong_match": "adopt_global",
        "existing_market_product": "update_existing",
        "new_market_local": "create_local",
    }.get(row["state"], "skip")


async def _apply_row(
    session: AsyncSession, *, market_id: UUID, row: dict, action: str, decision: ImportRowDecision | None
) -> MarketProduct:
    normalized = row["normalized"]
    price = Decimal(normalized["price"]) if normalized.get("price") else None
    promo_price = Decimal(normalized["promo_price"]) if normalized.get("promo_price") else None
    currency = normalized.get("currency") or "EUR"
    image_url = normalized.get("image_url")

    if action == "adopt_global":
        product_id = decision.target_id if decision and decision.target_id else None
        if product_id is None:
            candidates = (row.get("global_match") or {}).get("candidates") or []
            if len(candidates) == 1:
                product_id = UUID(candidates[0]["product_id"])
        if product_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Satır {row['row']}: hedef global ürün belirtilmedi.",
            )
        extra: dict[str, Any] = {}
        if image_url:
            extra["image_url"] = image_url
        return await catalog.adopt_global_product(
            session,
            market_id=market_id,
            product_id=product_id,
            regular_price=price,
            promo_price=promo_price,
            currency=currency,
            **extra,
        )

    if action == "create_local":
        extra = {
            "private_brand_text": normalized.get("brand"),
            "private_barcode": normalized.get("barcode"),
            "private_sku": normalized.get("sku"),
            "private_package_size": normalized.get("package_size"),
            "package_amount": Decimal(normalized["package_amount"]) if normalized.get("package_amount") else None,
            "package_unit": normalized.get("package_unit"),
            "package_type_canonical": normalized.get("package_type"),
            "category_override_id": UUID(normalized["category_id"]) if normalized.get("category_id") else None,
        }
        if image_url:
            extra["image_url"] = image_url
        return await catalog.create_private_market_product(
            session,
            market_id=market_id,
            private_name=normalized["product_name"],
            regular_price=price,
            promo_price=promo_price,
            currency=currency,
            allow_global_match_override=True,
            **{key: value for key, value in extra.items() if value is not None},
        )

    if action == "update_existing":
        market_product_id = decision.target_id if decision and decision.target_id else row.get("existing_market_product_id")
        if not market_product_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Satır {row['row']}: güncellenecek market ürünü bulunamadı.",
            )
        fields: dict[str, Any] = {}
        if "price" in row["original"]:
            fields["regular_price"] = price
        if "promo_price" in row["original"]:
            fields["promo_price"] = promo_price
        if "currency" in row["original"]:
            fields["currency"] = currency
        payload = MarketProductUpdate(**fields)
        return await catalog.update_market_product(session, UUID(str(market_product_id)), market_id, payload)

    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Bilinmeyen işlem: {action}.")


async def commit_import(
    session: AsyncSession,
    *,
    market_id: UUID,
    admin: PlatformAdmin,
    import_id: UUID,
    decisions: dict[int, ImportRowDecision],
) -> dict:
    job = await session.get(MarketCatalogImport, import_id)
    if job is None or job.market_id != market_id:
        raise _not_found("Import")
    if job.status != "previewed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Import is already '{job.status}' and cannot be committed again.",
        )
    now = utc_now()
    if job.expires_at is not None and now > job.expires_at:
        job.status = "expired"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Preview has expired. Please generate a new preview before committing.",
        )
    if await session.get(Market, market_id) is None:
        raise _not_found("Market")

    rows: list[dict] = list(job.preview_payload or [])
    import_id_value = job.id

    results: list[dict] = []
    imported = updated = skipped = failed = 0
    for row in rows:
        row_number = row["row"]
        decision = decisions.get(row_number)
        action = decision.action if decision else _default_action(row)
        if action == "skip" or (decision is None and row["state"] in _BLOCKING_STATES):
            skipped += 1
            results.append({"row": row_number, "outcome": "skipped", "action": action})
            continue
        try:
            market_product = await _apply_row(session, market_id=market_id, row=row, action=action, decision=decision)
        except HTTPException as exc:
            failed += 1
            results.append({"row": row_number, "outcome": "failed", "action": action, "error": str(exc.detail)})
            continue
        if action == "update_existing":
            updated += 1
        else:
            imported += 1
        results.append(
            {
                "row": row_number,
                "outcome": "success",
                "action": action,
                "market_product_id": str(market_product.id),
            }
        )

    job = await session.get(MarketCatalogImport, import_id_value)
    job.status = "committed"
    job.imported_rows = imported
    job.updated_rows = updated
    job.skipped_rows = skipped
    job.failed_rows = failed
    job.result_payload = results
    job.preview_payload = None
    job.completed_at = utc_now()
    session.add(
        PlatformAuditLog(
            actor_platform_admin_id=admin.id,
            action="market_catalog_import_committed",
            target_type="market",
            target_id=market_id,
            metadata_={
                "import_id": str(import_id_value),
                "filename": job.original_filename,
                "total_rows": job.total_rows,
                "imported_rows": imported,
                "updated_rows": updated,
                "skipped_rows": skipped,
                "failed_rows": failed,
            },
        )
    )
    session.add(
        ActivityLog(
            market_id=market_id,
            entity_type="market_catalog_import",
            entity_id=import_id_value,
            action="market_catalog_import_committed",
            description="market catalog import committed",
            metadata_={"imported_rows": imported, "updated_rows": updated, "failed_rows": failed},
        )
    )
    await session.commit()
    return {
        "import_id": str(import_id_value),
        "market_id": str(market_id),
        "status": "committed",
        "total_rows": len(rows),
        "imported_rows": imported,
        "updated_rows": updated,
        "skipped_rows": skipped,
        "failed_rows": failed,
        "rows": results,
    }
