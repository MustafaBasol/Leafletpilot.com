"""Layered, fail-closed validation of AI-generated brochure images."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

OCR_MIN_CONFIDENCE = 55.0
PRICE_TOKEN_MIN_CONFIDENCE = 70.0
_GENERIC_PRODUCT_TOKENS = {
    "campaign",
    "current",
    "discount",
    "fiyat",
    "indirim",
    "market",
    "old",
    "price",
    "product",
    "urun",
}


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
    words: tuple[str, ...]
    word_confidences: tuple[float, ...]
    passes: tuple[dict[str, Any], ...]



def _norm(value: object) -> str:
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^0-9a-z]", "", value)


def _tokens(value: object) -> list[str]:
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", value)


def _discriminative_tokens(value: object) -> list[str]:
    return [
        token
        for token in _tokens(value)
        if len(token) >= 3 and token not in _GENERIC_PRODUCT_TOKENS
    ]


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
        return _OCREvidence(False, 0.0, "", (), (), ())
    reports: list[dict[str, Any]] = []
    candidates: list[tuple[int, float, int, str, tuple[str, ...], tuple[float, ...]]] = []
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
                    confidence = 0.0
                confidences.append(max(confidence, 0.0))
            normalized = _norm(" ".join(words))
            matched_count = sum(
                1
                for fact in facts
                if _fact_is_matched(fact, tuple(words), tuple(confidences))
            )
            confidence = sum(confidences) / len(confidences) if confidences else 0.0
            reports.append(
                {
                    "name": name,
                    "confidence": round(confidence, 2),
                    "matched_fact_count": matched_count,
                    "recognized_character_count": len(normalized),
                }
            )
            candidates.append(
                (matched_count, confidence, len(normalized), normalized, tuple(words), tuple(confidences))
            )
        except Exception:  # noqa: BLE001 - a secondary pass may still succeed
            reports.append({"name": name, "status": "unavailable"})
    if not candidates:
        return _OCREvidence(False, 0.0, "", (), (), tuple(reports))
    _, confidence, _, normalized, words, confidences = max(candidates, key=lambda item: item[:3])
    return _OCREvidence(True, confidence, normalized, words, confidences, tuple(reports))


def _price_decimal(value: object) -> Decimal | None:
    raw = re.sub(r"[^0-9,.-]", "", str(value or "")).replace("-", "")
    if not raw or not re.search(r"[0-9]", raw):
        return None
    if "," in raw and "." in raw:
        separator = "," if raw.rfind(",") > raw.rfind(".") else "."
        integer, fraction = raw.rsplit(separator, 1)
        integer = integer.replace(",", "").replace(".", "")
        raw = f"{integer}.{fraction}"
    elif "," in raw or "." in raw:
        separator = "," if "," in raw else "."
        parts = raw.split(separator)
        if len(parts) == 2 and len(parts[1]) <= 2:
            raw = f"{parts[0]}.{parts[1]}"
        else:
            raw = "".join(parts)
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _numeric_price_candidates(
    words: tuple[str, ...], confidences: tuple[float, ...]
) -> list[tuple[Decimal, int, float]]:
    candidates: list[tuple[Decimal, int, float]] = []
    for index, word in enumerate(words):
        for value in re.findall(r"[0-9]+(?:[.,][0-9]{1,2})?", word):
            parsed = _price_decimal(value)
            if parsed is not None:
                confidence = confidences[index] if index < len(confidences) else 0.0
                if value.isdigit() and len(value) >= 3:
                    confidence = 0.0
                candidates.append((parsed, index, confidence))
    for index in range(len(words) - 1):
        first = re.fullmatch(r"[0-9]{1,3}", words[index])
        second = re.fullmatch(r"[0-9]{2}", words[index + 1])
        if first and second:
            parsed = _price_decimal(f"{first.group()}.{second.group()}")
            if parsed is not None:
                confidence = min(
                    confidences[index] if index < len(confidences) else 0.0,
                    confidences[index + 1] if index + 1 < len(confidences) else 0.0,
                )
                candidates.append((parsed, index, confidence))
    return candidates


def _product_position(value: object, words: tuple[str, ...]) -> int | None:
    expected = _discriminative_tokens(value)
    if not expected:
        return None
    normalized_words = [_tokens(word) for word in words]
    flattened_positions = [
        (token, index)
        for index, group in enumerate(normalized_words)
        for token in group
    ]
    flattened = [token for token, _ in flattened_positions]

    def first_position(token: str) -> int:
        return next(index for candidate, index in flattened_positions if candidate == token)

    for start, (token, raw_index) in enumerate(flattened_positions):
        if token != expected[0]:
            continue
        cursor = start + 1
        matched_end = start
        for target in expected[1:]:
            while (
                cursor < len(flattened_positions)
                and flattened_positions[cursor][0] != target
                and cursor - matched_end <= 4
            ):
                cursor += 1
            if cursor >= len(flattened_positions) or flattened_positions[cursor][0] != target:
                break
            matched_end = cursor
            cursor += 1
        else:
            return raw_index

    if all(token in flattened for token in expected):
        positions = [first_position(token) for token in expected]
        if positions == sorted(positions):
            return min(positions)
    matched = [token for token in expected if token in flattened]
    if len(expected) >= 2 and len(matched) >= 2 and len(matched) / len(expected) >= 0.5:
        return min(first_position(token) for token in matched)
    if len(expected) == 1 and len(matched) == 1:
        return first_position(matched[0])
    if len(matched) == 1 and len(matched[0]) >= 6:
        return first_position(matched[0])
    return None


def _fact_is_matched(
    fact: _ExpectedFact, words: tuple[str, ...], confidences: tuple[float, ...]
) -> bool:
    if fact.category == "product_name":
        return _product_position(fact.value, words) is not None
    if fact.category in {"current_price", "old_price"}:
        expected = _price_decimal(fact.value)
        return expected is not None and any(
            value == expected and confidence >= PRICE_TOKEN_MIN_CONFIDENCE
            for value, _, confidence in _numeric_price_candidates(words, confidences)
        )
    return _norm(fact.value) in _norm(" ".join(words))


def _product_order(snapshot: dict[str, Any], text: str | list[str]) -> bool | None:
    words = tuple(text.split()) if isinstance(text, str) else tuple(text)
    positions = [
        _product_position(item.get("name"), words)
        for item in snapshot.get("items") or []
        if item.get("name")
    ]
    if len(positions) < 2 or any(position is None for position in positions):
        return None
    return positions == sorted(positions)


def _associated_price_candidates(
    position: int | None,
    candidates: list[tuple[Decimal, int, float]],
) -> list[tuple[Decimal, int, float]]:
    if position is None:
        return []
    nearby = [
        candidate
        for candidate in candidates
        if candidate[1] > position
        and candidate[1] - position <= 12
        and candidate[2] >= PRICE_TOKEN_MIN_CONFIDENCE
    ]
    if nearby:
        return nearby
    return []


def _product_conflict(
    expected: str,
    words: tuple[str, ...],
    other_product_matched: bool,
    non_product_tokens: set[str],
) -> bool:
    if other_product_matched:
        return False
    expected_tokens = set(_discriminative_tokens(expected))
    observed = [token for token in _tokens(" ".join(words)) if len(token) >= 4]
    unknown = [
        token
        for token in observed
        if token not in expected_tokens
        and token not in non_product_tokens
        and token not in _GENERIC_PRODUCT_TOKENS
        and not token.isdigit()
    ]
    if not unknown:
        return False
    for index in range(len(observed) - 1):
        pair = observed[index : index + 2]
        if any(token in unknown for token in pair) and any(
            token in expected_tokens for token in pair
        ):
            return True
    return len(unknown) >= 2


def _fact_states(
    snapshot: dict[str, Any],
    facts: list[_ExpectedFact],
    evidence: _OCREvidence,
) -> dict[str, str]:
    words = evidence.words
    confidences = evidence.word_confidences
    states = {_fact_token(fact): "unreadable" for fact in facts}
    products = [item for item in snapshot.get("items") or [] if item.get("name")]
    product_positions = [
        _product_position(item.get("name"), words) for item in products
    ]
    product_matches = [position is not None for position in product_positions]
    non_product_tokens = {
        token
        for fact in facts
        if fact.category != "product_name"
        for token in _tokens(fact.value)
    }
    for index, fact in enumerate(facts):
        token = _fact_token(fact)
        if fact.category == "product_name":
            position = _product_position(fact.value, words)
            if position is not None:
                states[token] = "matched"
            elif _product_conflict(
                fact.value,
                words,
                any(product_matches),
                non_product_tokens,
            ):
                states[token] = "conflicting"
            continue
        if fact.category not in {"current_price", "old_price"}:
            if _fact_is_matched(fact, words, confidences):
                states[token] = "matched"
            continue
        item = next(
            (
                candidate
                for candidate in products
                if candidate.get("price" if fact.category == "current_price" else "old_price")
                == fact.value
            ),
            None,
        )
        position = _product_position(item.get("name"), words) if item else None
        associated = _associated_price_candidates(
            position, _numeric_price_candidates(words, confidences)
        )
        expected = _price_decimal(fact.value)
        if expected is None:
            continue
        if any(value == expected for value, _, _ in associated):
            states[token] = "matched"
        elif associated and not any(
            value
            in {
                parsed
                for parsed in (
                    _price_decimal(item.get("price")) if item else None,
                    _price_decimal(item.get("old_price")) if item else None,
                )
                if parsed is not None
            }
            for value, _, _ in associated
        ):
            states[token] = "conflicting"
    return states


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
        "version": 3,
        "accepted": False,
        "evidence_status": "technical_failure",
        "critical_facts": {},
    }
    image = _technical_image(image_bytes, report)
    if image is None:
        return BrochureValidationResult(False, report)
    facts = _required_fact_records(snapshot)
    evidence = _ocr_evidence(image, facts)
    states = _fact_states(snapshot, facts, evidence)
    matched = [fact for fact in facts if states[_fact_token(fact)] == "matched"]
    unreadable = [fact for fact in facts if states[_fact_token(fact)] == "unreadable"]
    conflicting = [fact for fact in facts if states[_fact_token(fact)] == "conflicting"]
    order_ok = _product_order(snapshot, list(evidence.words))
    category_counts: dict[str, dict[str, int]] = {}
    for fact in facts:
        counts = category_counts.setdefault(
            fact.category,
            {"required": 0, "matched": 0, "unreadable": 0, "conflicting": 0},
        )
        counts["required"] += 1
        counts[states[_fact_token(fact)]] += 1
    report["ocr"] = {
        "available": evidence.available,
        "confidence": round(evidence.confidence, 2),
        "minimum_confidence": OCR_MIN_CONFIDENCE,
        "passes": list(evidence.passes),
    }
    report["critical_facts"] = {
        "required_count": len(facts),
        "matched_count": len(matched),
        "unreadable_count": len(unreadable),
        "conflicting_count": len(conflicting),
        "missing_count": len(unreadable),
        "missing_categories": sorted({fact.category for fact in unreadable}),
        "missing_fact_tokens": [_fact_token(fact) for fact in unreadable],
        "conflicting_categories": sorted({fact.category for fact in conflicting}),
        "conflicting_fact_tokens": [_fact_token(fact) for fact in conflicting],
        "category_counts": category_counts,
        "product_order": order_ok,
    }
    if not evidence.available:
        report.update(evidence_status="unverifiable", reason="ocr_unavailable")
        return BrochureValidationResult(False, report)
    if evidence.confidence < OCR_MIN_CONFIDENCE:
        report.update(evidence_status="unverifiable", reason="ocr_low_confidence")
        return BrochureValidationResult(False, report)
    if conflicting or order_ok is False:
        report.update(evidence_status="mismatch", reason="commercial_fact_mismatch")
        return BrochureValidationResult(False, report)
    product_count = sum(1 for item in snapshot.get("items") or [] if item.get("name"))
    if unreadable or (product_count >= 2 and order_ok is None):
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
