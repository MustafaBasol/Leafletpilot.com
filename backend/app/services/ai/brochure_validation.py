"""Layered, fail-closed validation of AI-generated brochure images."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

OCR_MIN_CONFIDENCE = 55.0
MIN_MATCH_RATIO_FOR_MISMATCH = 0.65


@dataclass(frozen=True)
class BrochureValidationResult:
    accepted: bool
    report: dict[str, Any]


@dataclass(frozen=True)
class _ExpectedFact:
    category: str
    value: str


@dataclass(frozen=True)
class _OCREvidence:
    available: bool
    confidence: float
    normalized_text: str
    matched: tuple[_ExpectedFact, ...]
    passes: tuple[dict[str, Any], ...]


def _norm(value: object) -> str:
    return re.sub(r"[^0-9a-zçğıöşü€$£]", "", str(value or "").casefold())


def _required_fact_records(snapshot: dict[str, Any]) -> list[_ExpectedFact]:
    facts: list[_ExpectedFact] = []

    def add(category: str, value: object) -> None:
        if value not in (None, ""):
            facts.append(_ExpectedFact(category, str(value)))

    add("market_identity", snapshot.get("market_name"))
    add("campaign_title", snapshot.get("title"))
    profile = snapshot.get("market_profile") or {}
    visibility = profile.get("visibility") or {}
    add("market_identity", profile.get("name"))
    for key in ("address", "phone", "website", "instagram", "facebook"):
        if visibility.get(key):
            add(f"market_{key}", profile.get(key))
    header = snapshot.get("header") or {}
    add("campaign_date", header.get("validity_text"))
    add("required_footer", header.get("footer_note"))
    for item in snapshot.get("items") or []:
        add("product_name", item.get("name"))
        add("current_price", item.get("price"))
        add("old_price", item.get("old_price"))
        add("unit_fact", item.get("unit_label"))
        add("package_fact", item.get("quantity_label"))
    return list({(fact.category, fact.value): fact for fact in facts}.values())


def _required_facts(snapshot: dict[str, Any]) -> list[str]:
    """Compatibility helper used by focused market-profile tests."""
    return [fact.value for fact in _required_fact_records(snapshot)]


def _fact_token(fact: _ExpectedFact) -> str:
    return hashlib.sha256(f"{fact.category}:{fact.value}".encode()).hexdigest()[:12]


def _technical_image(image_bytes: bytes, report: dict[str, Any]) -> Image.Image | None:
    try:
        with Image.open(BytesIO(image_bytes)) as opened:
            opened.load()
            image = opened.convert("RGB")
            width, height = image.size
            source_format = opened.format
    except (UnidentifiedImageError, OSError, ValueError):
        report["technical"] = {"status": "failed", "reason": "image_unreadable"}
        report["reason"] = "image_unreadable"
        return None
    ratio = width / height if height else 0
    report["technical"] = {
        "status": "verified",
        "format": source_format,
        "width": width,
        "height": height,
        "aspect_ratio": round(ratio, 4),
    }
    if width < 900 or height < 1200 or width > 4096 or height > 6144:
        report["technical"].update(status="failed", reason="unsupported_dimensions")
        report["reason"] = "unsupported_dimensions"
        return None
    if not 0.5 <= ratio <= 0.85:
        report["technical"].update(status="failed", reason="unsupported_aspect_ratio")
        report["reason"] = "unsupported_aspect_ratio"
        return None
    low, high = ImageStat.Stat(image.convert("L")).extrema[0]
    if high - low < 4:
        report["technical"].update(status="failed", reason="image_empty")
        report["reason"] = "image_empty"
        return None
    return image


def _ocr_variants(image: Image.Image) -> list[tuple[str, Image.Image]]:
    variants = [("original", image)]
    scale = min(2.0, 2600 / max(image.size))
    if scale > 1.05:
        variants.append(
            (
                "scaled",
                image.resize(
                    (round(image.width * scale), round(image.height * scale)),
                    Image.Resampling.LANCZOS,
                ),
            )
        )
    gray = ImageOps.autocontrast(image.convert("L"))
    variants.extend(
        [
            ("contrast", gray),
            ("threshold", gray.point(lambda value: 255 if value >= 165 else 0)),
        ]
    )
    return variants


def _ocr_evidence(image: Image.Image, facts: list[_ExpectedFact]) -> _OCREvidence:
    try:
        import pytesseract
    except Exception:  # noqa: BLE001 - optional OCR remains fail-closed
        return _OCREvidence(False, 0.0, "", (), ())
    reports: list[dict[str, Any]] = []
    candidates: list[tuple[int, float, int, str, tuple[_ExpectedFact, ...]]] = []
    for name, variant in _ocr_variants(image):
        try:
            data = pytesseract.image_to_data(
                variant, config="--psm 6", output_type=pytesseract.Output.DICT
            )
            words: list[str] = []
            confidences: list[float] = []
            for text, raw_conf in zip(data.get("text", []), data.get("conf", []), strict=False):
                text = str(text or "").strip()
                if not text:
                    continue
                words.append(text)
                try:
                    confidence = float(raw_conf)
                except (TypeError, ValueError):
                    continue
                if confidence >= 0:
                    confidences.append(confidence)
            normalized = _norm(" ".join(words))
            matched = tuple(fact for fact in facts if _norm(fact.value) in normalized)
            confidence = sum(confidences) / len(confidences) if confidences else 0.0
            reports.append(
                {
                    "name": name,
                    "confidence": round(confidence, 2),
                    "matched_fact_count": len(matched),
                    "recognized_character_count": len(normalized),
                }
            )
            candidates.append((len(matched), confidence, len(normalized), normalized, matched))
        except Exception:  # noqa: BLE001 - a secondary pass may still succeed
            reports.append({"name": name, "status": "unavailable"})
    if not candidates:
        return _OCREvidence(False, 0.0, "", (), tuple(reports))
    _, confidence, _, normalized, matched = max(candidates, key=lambda item: item[:3])
    return _OCREvidence(True, confidence, normalized, matched, tuple(reports))


def _product_order(snapshot: dict[str, Any], text: str) -> bool | None:
    names = [_norm(item.get("name")) for item in snapshot.get("items") or [] if item.get("name")]
    positions = [text.find(name) for name in names]
    if any(position < 0 for position in positions):
        return None
    return positions == sorted(positions)


def _logo_similarity(image: Image.Image, logo_bytes: bytes) -> float:
    """Conservative coarse signal; absence is unverifiable, never a mismatch."""
    try:
        with Image.open(BytesIO(logo_bytes)) as opened:
            logo = opened.convert("RGBA")
            base = Image.new("RGBA", logo.size, "white")
            base.alpha_composite(logo)
            reference = ImageOps.autocontrast(base.convert("L")).resize((16, 16))
    except (UnidentifiedImageError, OSError, ValueError):
        return 0.0
    canvas = image.crop((0, 0, image.width, round(image.height * 0.5)))
    best = 0.0
    for width in (48, 64, 80, 112, 144, 192):
        height = max(24, round(width * logo.height / max(logo.width, 1)))
        if width > canvas.width or height > canvas.height:
            continue
        for top in range(0, canvas.height - height + 1, max(12, height // 3)):
            for left in range(0, canvas.width - width + 1, max(12, width // 3)):
                probe = ImageOps.autocontrast(
                    canvas.crop((left, top, left + width, top + height)).convert("L")
                ).resize((16, 16))
                delta = sum(
                    abs(a - b) for a, b in zip(reference.getdata(), probe.getdata(), strict=True)
                ) / (256 * 255)
                best = max(best, 1.0 - delta)
    return round(best, 4)


def validate_generated_brochure(
    image_bytes: bytes,
    snapshot: dict[str, Any],
    *,
    logo_required: bool,
    logo_image: bytes | None = None,
) -> BrochureValidationResult:
    report: dict[str, Any] = {
        "version": 2,
        "accepted": False,
        "evidence_status": "technical_failure",
        "critical_facts": {},
    }
    image = _technical_image(image_bytes, report)
    if image is None:
        return BrochureValidationResult(False, report)
    facts = _required_fact_records(snapshot)
    evidence = _ocr_evidence(image, facts)
    matched_tokens = {_fact_token(fact) for fact in evidence.matched}
    missing = [fact for fact in facts if _fact_token(fact) not in matched_tokens]
    ratio = len(evidence.matched) / len(facts) if facts else 1.0
    order_ok = _product_order(snapshot, evidence.normalized_text)
    report["ocr"] = {
        "available": evidence.available,
        "confidence": round(evidence.confidence, 2),
        "minimum_confidence": OCR_MIN_CONFIDENCE,
        "passes": list(evidence.passes),
    }
    report["critical_facts"] = {
        "required_count": len(facts),
        "matched_count": len(evidence.matched),
        "missing_count": len(missing),
        "missing_categories": sorted({fact.category for fact in missing}),
        "missing_fact_tokens": [_fact_token(fact) for fact in missing],
        "product_order": order_ok,
    }
    if not evidence.available:
        report.update(evidence_status="unverifiable", reason="ocr_unavailable")
        return BrochureValidationResult(False, report)
    if evidence.confidence < OCR_MIN_CONFIDENCE:
        report.update(evidence_status="unverifiable", reason="ocr_low_confidence")
        return BrochureValidationResult(False, report)
    if order_ok is False or (missing and ratio >= MIN_MATCH_RATIO_FOR_MISMATCH):
        report.update(evidence_status="mismatch", reason="commercial_fact_mismatch")
        return BrochureValidationResult(False, report)
    if missing or order_ok is None:
        report.update(evidence_status="unverifiable", reason="critical_facts_unverifiable")
        return BrochureValidationResult(False, report)
    if logo_required:
        similarity = _logo_similarity(image, logo_image) if logo_image else 0.0
        report["logo_identity"] = {
            "status": "verified" if similarity >= 0.92 else "unverifiable",
            "similarity": similarity,
        }
        if similarity < 0.92:
            report.update(evidence_status="unverifiable", reason="logo_identity_unverifiable")
            return BrochureValidationResult(False, report)
    report.update(accepted=True, evidence_status="verified", reason="passed")
    return BrochureValidationResult(True, report)
