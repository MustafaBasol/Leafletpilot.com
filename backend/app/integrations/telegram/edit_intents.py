from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class FlyerEditKind(StrEnum):
    CHANGE_HERO_PRODUCT = "change_hero_product"
    REDUCE_PRODUCT_EMPHASIS = "reduce_product_emphasis"
    ADJUST_VISUAL_DENSITY = "adjust_visual_density"
    INCREASE_PRICE_PROMINENCE = "increase_price_prominence"
    REGROUP_PRODUCTS = "regroup_products"
    REMOVE_PRODUCT = "remove_product"
    SET_TITLE = "set_title"
    RERENDER_CURRENT_CAMPAIGN = "rerender_current_campaign"
    CHANGE_FORMAT = "change_format"


@dataclass(frozen=True)
class FlyerEditIntent:
    kind: FlyerEditKind
    product_reference: str | None = None
    value: str | None = None
    source_text: str = ""

    def as_dict(self) -> dict[str, str | None]:
        return {
            "kind": self.kind.value,
            "product_reference": self.product_reference,
            "value": self.value,
            "source_text": self.source_text,
        }


_APOSTROPHE_SUFFIX = r"(?:['’](?:nın|nin|nun|nün|y[ıiuü]|i|ı|u|ü|yi|yı|yu|yü|ni|nı|nu|nü))?"


def normalize_for_match(value: str) -> str:
    translated = value.casefold().translate(str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"}))
    decomposed = unicodedata.normalize("NFKD", translated)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", decomposed).split())


def parse_flyer_edit_intent(text: str) -> FlyerEditIntent | None:
    source = " ".join(text.strip().split())
    normalized = normalize_for_match(source)
    if not normalized:
        return None

    title = _title_value(source)
    if title:
        return FlyerEditIntent(FlyerEditKind.SET_TITLE, value=title, source_text=source)

    if re.search(r"\b(pdf|pdf gonder|pdf gönder)\b", source, re.IGNORECASE):
        return FlyerEditIntent(FlyerEditKind.CHANGE_FORMAT, value="pdf", source_text=source)
    if "instagram hikaye" in normalized or "story" in normalized:
        return FlyerEditIntent(FlyerEditKind.CHANGE_FORMAT, value="instagram_story", source_text=source)
    if "instagram" in normalized:
        return FlyerEditIntent(FlyerEditKind.CHANGE_FORMAT, value="instagram_post", source_text=source)
    if "whatsapp" in normalized:
        return FlyerEditIntent(FlyerEditKind.CHANGE_FORMAT, value="whatsapp", source_text=source)

    reference = _reference_before_action(source, r"(?:daha\s+(?:az\s+)?öne\s+çıkar|küçült|vurgusunu\s+azalt)")
    if reference:
        return FlyerEditIntent(FlyerEditKind.REDUCE_PRODUCT_EMPHASIS, product_reference=reference, source_text=source)

    reference = _reference_before_action(source, r"(?:daha\s+büyük\s+yap|büyüt|öne\s+çıkar|hero\s+yap)")
    if reference:
        return FlyerEditIntent(FlyerEditKind.CHANGE_HERO_PRODUCT, product_reference=reference, source_text=source)

    reference = _reference_before_action(source, r"(?:kaldır|çıkar|sil)")
    if reference:
        return FlyerEditIntent(FlyerEditKind.REMOVE_PRODUCT, product_reference=reference, source_text=source)

    group_match = re.match(r"(.+?)\s+(?:ürünlerini|urunlerini)?\s*(?:aynı|ayni)\s+gruba\s+al", source, re.IGNORECASE)
    if group_match:
        reference = _clean_reference(group_match.group(1))
        return FlyerEditIntent(FlyerEditKind.REGROUP_PRODUCTS, product_reference=reference or None, source_text=source)
    if "benzer urunleri grupla" in normalized or "urunleri grupla" in normalized:
        return FlyerEditIntent(FlyerEditKind.REGROUP_PRODUCTS, source_text=source)

    if any(phrase in normalized for phrase in ("daha sade", "sadelestir", "kalabalik olmus", "az kalabalik")):
        return FlyerEditIntent(FlyerEditKind.ADJUST_VISUAL_DENSITY, value="simpler", source_text=source)
    if any(phrase in normalized for phrase in ("daha dikkat cekici", "daha canli", "goze carpan")):
        return FlyerEditIntent(FlyerEditKind.ADJUST_VISUAL_DENSITY, value="eye_catching", source_text=source)
    if any(phrase in normalized for phrase in ("fiyatlari daha gorunur", "fiyatlari buyut", "fiyatlari one cikar", "fiyat vurgusu")):
        return FlyerEditIntent(FlyerEditKind.INCREASE_PRICE_PROMINENCE, value="high", source_text=source)
    if any(phrase in normalized for phrase in ("yeniden olustur", "yeniden uret", "tekrar olustur", "tekrar render", "rerender")):
        return FlyerEditIntent(FlyerEditKind.RERENDER_CURRENT_CAMPAIGN, source_text=source)
    return None


def _title_value(source: str) -> str | None:
    patterns = (
        r"^(?:başlığı|basligi)\s+(?:değiştir|degistir)\s*[:\-]?\s*(.+)$",
        r"^(?:başlık|baslik)\s*[:\-]\s*(.+)$",
        r"^(?:başlığı|basligi)\s+(.+?)\s+yap$",
    )
    for pattern in patterns:
        match = re.match(pattern, source, re.IGNORECASE)
        if match:
            value = match.group(1).strip(" .\"'")
            if normalize_for_match(value) in {"daha dikkat cekici", "daha carpici"}:
                return None
            return value[:255] or None
    return None


def _reference_before_action(source: str, action: str) -> str | None:
    match = re.match(rf"(.+?){_APOSTROPHE_SUFFIX}\s+{action}(?:\s+lütfen)?[.!]?\s*$", source, re.IGNORECASE)
    if not match:
        return None
    value = _clean_reference(match.group(1))
    return value or None


def _clean_reference(value: str) -> str:
    return re.sub(r"\s+(?:ürününü|urununu|ürünü|urunu|ürünlerini|urunlerini)$", "", value, flags=re.IGNORECASE).strip(" .\"'")
