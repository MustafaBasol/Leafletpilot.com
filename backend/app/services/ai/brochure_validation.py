"""Fail-closed validation of AI-generated brochure images."""
from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, UnidentifiedImageError


@dataclass(frozen=True)
class BrochureValidationResult:
    accepted: bool
    report: dict[str, Any]


def _norm(value: object) -> str:
    return re.sub(r"[^0-9a-zçğıöşü€$£]", "", str(value or "").casefold())


def _required_facts(snapshot: dict[str, Any]) -> list[str]:
    facts = [snapshot.get("market_name"), snapshot.get("title")]
    profile = snapshot.get("market_profile") or {}
    visibility = profile.get("visibility") or {}
    facts.append(profile.get("name"))
    for key in ("address", "phone", "website", "instagram", "facebook"):
        if visibility.get(key):
            facts.append(profile.get(key))
    header = snapshot.get("header") or {}
    facts.extend([header.get("validity_text"), header.get("footer_note")])
    for item in snapshot.get("items") or []:
        facts.extend([item.get("name"), item.get("price"), item.get("old_price"), item.get("unit_label"), item.get("quantity_label")])
    return [str(value) for value in facts if value not in (None, "")]


def validate_generated_brochure(image_bytes: bytes, snapshot: dict[str, Any], *, logo_required: bool) -> BrochureValidationResult:
    report: dict[str, Any] = {"version": 1, "accepted": False, "checks": {}, "missing_facts": [], "warnings": []}
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError):
        report["checks"]["image_readable"] = False
        report["reason"] = "image_unreadable"
        return BrochureValidationResult(False, report)
    report["checks"]["image_readable"] = True
    report["image_dimensions"] = {"width": width, "height": height}
    if width < 900 or height < 1200:
        report["reason"] = "image_too_small"
        return BrochureValidationResult(False, report)
    try:
        import pytesseract  # optional deployment dependency; absence fails closed
        extracted = pytesseract.image_to_string(Image.open(BytesIO(image_bytes)), config="--psm 6")
    except Exception:  # noqa: BLE001 - optional OCR must fail closed
        report["checks"]["ocr_available"] = False
        report["reason"] = "ocr_unavailable_or_low_confidence"
        return BrochureValidationResult(False, report)
    normalized_text = _norm(extracted)
    missing = [fact for fact in _required_facts(snapshot) if _norm(fact) not in normalized_text]
    report["checks"]["ocr_available"] = True
    report["checks"]["immutable_text"] = not missing
    report["missing_facts"] = missing
    product_names = [_norm(item.get("name")) for item in snapshot.get("items") or [] if item.get("name")]
    found_positions = [normalized_text.find(name) for name in product_names]
    order_ok = all(position >= 0 for position in found_positions) and found_positions == sorted(found_positions)
    report["checks"]["product_order"] = order_ok
    if logo_required:
        # OCR cannot prove graphic identity. Require an explicit visual-review capability
        # in a later provider adapter; until then this remains a rejection, never a guess.
        report["checks"]["logo_identity"] = False
        report["reason"] = "logo_identity_not_verifiable"
        return BrochureValidationResult(False, report)
    accepted = not missing and order_ok
    report["accepted"] = accepted
    report["reason"] = "passed" if accepted else "immutable_facts_missing_or_reordered"
    return BrochureValidationResult(accepted, report)