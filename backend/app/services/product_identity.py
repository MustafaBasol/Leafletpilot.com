from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_TURKISH_TRANSLATION = str.maketrans(
    {
        "\u00e7": "c",
        "\u00c7": "c",
        "\u011f": "g",
        "\u011e": "g",
        "\u0131": "i",
        "\u0130": "i",
        "\u00f6": "o",
        "\u00d6": "o",
        "\u015f": "s",
        "\u015e": "s",
        "\u00fc": "u",
        "\u00dc": "u",
    }
)
_SPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^a-z0-9%.,]+")
_LOOSE_PUNCTUATION_RE = re.compile(r"(?<!\d)[.,]|[.,](?!\d)")
_QUANTITY_RE = re.compile(
    r"(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*"
    r"(kilograms?|kilogram|kilo|kg|grams?|gram|gr|g|litres?|liters?|litre|liter|lt|l|ml)\b",
    re.IGNORECASE,
)
_PACK_RE = re.compile(
    r"(?<![a-z0-9])(?:x\s*(\d+)|(\d+)\s*(?:'\s*)?li|(?:paket|pack)\s*(\d+))(?![a-z0-9])",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(?:%\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*%)")

_UNIT_ALIASES = {
    "kilogram": "kg",
    "kilograms": "kg",
    "kilo": "kg",
    "kg": "kg",
    "gram": "g",
    "grams": "g",
    "gr": "g",
    "g": "g",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "lt": "l",
    "l": "l",
    "ml": "ml",
}
_VARIANT_ALIASES = {
    "zero": "zero",
    "seker siz": "sugar-free",
    "sekersiz": "sugar-free",
    "sugar free": "sugar-free",
    "original": "original",
    "orijinal": "original",
    "classic": "classic",
    "klasik": "classic",
    "kakao": "cocoa",
    "kakaolu": "cocoa",
    "cocoa": "cocoa",
    "cilek": "strawberry",
    "cilekli": "strawberry",
    "strawberry": "strawberry",
    "vanilya": "vanilla",
    "vanilyali": "vanilla",
    "vanilla": "vanilla",
    "light": "light",
    "diet": "diet",
    "diyet": "diet",
    "laktozsuz": "lactose-free",
    "lactose free": "lactose-free",
    "tam yagli": "full-fat",
    "full fat": "full-fat",
    "yarim yagli": "low-fat",
    "low fat": "low-fat",
    "acili": "spicy",
    "spicy": "spicy",
    "tuzlu": "salted",
    "salted": "salted",
    "tuzsuz": "unsalted",
    "unsalted": "unsalted",
}


@dataclass(frozen=True)
class NormalizedProductIdentity:
    original_name: str
    normalized_full_name: str
    brand: str | None
    normalized_brand: str | None
    product_family: str
    normalized_product_family: str
    variant: str | None
    normalized_variant: str | None
    quantity: str | None
    normalized_quantity: str | None
    unit: str | None
    normalized_unit: str | None
    pack_count: int | None
    search_tokens: tuple[str, ...]

    @property
    def size_key(self) -> str | None:
        if self.normalized_quantity is None or self.normalized_unit is None:
            return None
        return f"{self.normalized_quantity}{self.normalized_unit}"

    def as_dict(self) -> dict[str, str | int | list[str] | None]:
        return {
            "original_name": self.original_name,
            "normalized_full_name": self.normalized_full_name,
            "brand": self.brand,
            "normalized_brand": self.normalized_brand,
            "product_family": self.product_family,
            "normalized_product_family": self.normalized_product_family,
            "variant": self.variant,
            "normalized_variant": self.normalized_variant,
            "quantity": self.quantity,
            "normalized_quantity": self.normalized_quantity,
            "unit": self.unit,
            "normalized_unit": self.normalized_unit,
            "pack_count": self.pack_count,
            "search_tokens": list(self.search_tokens),
        }


def normalize_product_identity(
    value: str,
    *,
    brand: str | None = None,
    package_size: str | None = None,
) -> NormalizedProductIdentity:
    original = value.strip()
    normalized_brand = normalize_words(brand) if brand else None
    working = normalize_words(_identity_input(original, package_size))

    quantity, normalized_quantity, unit, normalized_unit = _extract_quantity(working)
    working = _QUANTITY_RE.sub(" ", working)
    pack_count = _extract_pack_count(working)
    working = _PACK_RE.sub(" ", working)
    working = _PERCENT_RE.sub(
        lambda match: f" {_decimal_text(match.group(1) or match.group(2))}% ",
        working,
    )
    working = _LOOSE_PUNCTUATION_RE.sub(" ", working)
    working = _SPACE_RE.sub(" ", working).strip()

    family_working = _remove_brand_prefix(working, normalized_brand)
    normalized_variant, family_working = _extract_variant(family_working)
    normalized_family = _SPACE_RE.sub(" ", family_working).strip()

    parts = [part for part in (normalized_brand, normalized_family, normalized_variant) if part]
    if normalized_quantity and normalized_unit:
        parts.append(f"{normalized_quantity}{normalized_unit}")
    if pack_count:
        parts.append(f"{pack_count}x")
    normalized_full = " ".join(dict.fromkeys(parts))
    tokens = tuple(
        dict.fromkeys(
            token
            for part in (normalized_brand, normalized_family, normalized_variant)
            if part
            for token in part.split()
            if len(token) >= 2
        )
    )

    return NormalizedProductIdentity(
        original_name=original,
        normalized_full_name=normalized_full,
        brand=brand.strip() if brand else None,
        normalized_brand=normalized_brand,
        product_family=normalized_family,
        normalized_product_family=normalized_family,
        variant=normalized_variant,
        normalized_variant=normalized_variant,
        quantity=quantity,
        normalized_quantity=normalized_quantity,
        unit=unit,
        normalized_unit=normalized_unit,
        pack_count=pack_count,
        search_tokens=tokens,
    )


def normalize_product_text(value: str) -> str:
    """Return the canonical full identity used by matching and alias storage."""
    return normalize_product_identity(value).normalized_full_name


def normalize_words(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value.translate(_TURKISH_TRANSLATION).casefold())
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = normalized.replace("%", " percent ")
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    normalized = normalized.replace(" percent ", "%")
    return _SPACE_RE.sub(" ", normalized).strip()


def _identity_input(value: str, package_size: str | None) -> str:
    if not package_size or _QUANTITY_RE.search(normalize_words(value)):
        return value
    return f"{value} {package_size}"


def _extract_quantity(value: str) -> tuple[str | None, str | None, str | None, str | None]:
    match = _QUANTITY_RE.search(value)
    if match is None:
        return None, None, None, None
    quantity = _decimal_text(match.group(1))
    unit = _UNIT_ALIASES[match.group(2).lower()]
    decimal_quantity = Decimal(quantity)
    if unit == "kg":
        decimal_quantity *= 1000
        normalized_unit = "g"
    elif unit == "l":
        decimal_quantity *= 1000
        normalized_unit = "ml"
    else:
        normalized_unit = unit
    return quantity, _format_decimal(decimal_quantity), unit, normalized_unit


def _extract_pack_count(value: str) -> int | None:
    match = _PACK_RE.search(value)
    if match is None:
        return None
    return int(next(group for group in match.groups() if group is not None))


def _extract_variant(value: str) -> tuple[str | None, str]:
    remaining = f" {value} "
    variants: list[str] = []
    for alias in sorted(_VARIANT_ALIASES, key=len, reverse=True):
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")
        if pattern.search(remaining):
            variants.append(_VARIANT_ALIASES[alias])
            remaining = pattern.sub(" ", remaining)
    normalized_variant = " ".join(dict.fromkeys(variants)) or None
    return normalized_variant, _SPACE_RE.sub(" ", remaining).strip()


def _remove_brand_prefix(value: str, brand: str | None) -> str:
    if not brand:
        return value
    if value == brand:
        return ""
    if value.startswith(f"{brand} "):
        return value[len(brand) + 1 :]
    return value


def _decimal_text(value: str) -> str:
    try:
        return _format_decimal(Decimal(value.replace(",", ".")))
    except InvalidOperation:
        return value.replace(",", ".")


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
