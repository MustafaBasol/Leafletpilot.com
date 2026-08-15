"""Small, deterministic normalizers for product catalogue input."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

PACKAGE_UNITS = ("g", "kg", "ml", "cl", "l", "pcs")
PACKAGE_TYPES = ("bottle", "can", "box", "bag", "jar", "packet")
CURRENCIES = ("EUR", "TRY", "USD", "GBP", "CHF")
_PACKAGE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(grammes?|gr|g|kilogrammes?|kilogram|kilo|kg|millilitres?|ml|cl|litres?|lt|l|pi[eè]ces?|pcs?|adet)\s*$", re.I)
_UNITS = {"g": "g", "gr": "g", "gram": "g", "gramme": "g", "grammes": "g", "kg": "kg", "kilo": "kg", "kilogram": "kg", "kilogramme": "kg", "kilogrammes": "kg", "ml": "ml", "millilitre": "ml", "millilitres": "ml", "cl": "cl", "l": "l", "lt": "l", "litre": "l", "litres": "l", "pc": "pcs", "pcs": "pcs", "adet": "pcs", "pièce": "pcs", "piece": "pcs", "pièces": "pcs", "pieces": "pcs"}
_TYPES = {"bottle": "bottle", "şişe": "bottle", "sise": "bottle", "can": "can", "teneke": "can", "box": "box", "kutu": "box", "bag": "bag", "poşet": "bag", "poset": "bag", "jar": "jar", "kavanoz": "jar", "packet": "packet", "paket": "packet"}


def normalize_currency(value: str | None, default: str = "EUR", *, strict: bool = False) -> str:
    if value is None or not str(value).strip():
        return default
    currency = str(value).strip().upper()
    if currency in CURRENCIES:
        return currency
    if strict:
        raise ValueError(f"Unsupported currency: {value}")
    return default


def normalize_package_unit(value: str | None, *, strict: bool = False) -> str | None:
    if value is None or not str(value).strip():
        return None
    unit = _UNITS.get(str(value).strip().casefold())
    if unit is None and strict:
        raise ValueError(f"Unsupported package unit: {value}")
    return unit


def parse_package(value: str | None, unit: str | None = None) -> tuple[Decimal | None, str | None]:
    if value:
        match = _PACKAGE.match(value)
        if match:
            try:
                return Decimal(match.group(1).replace(",", ".")), _UNITS[match.group(2).casefold()]
            except (InvalidOperation, KeyError):
                pass
    return None, normalize_package_unit(unit)


def format_package(amount: Decimal | None, unit: str | None, fallback: str | None = None) -> str | None:
    if amount is None or not unit:
        return fallback
    text = format(amount.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text} {unit}"


def normalize_package_type(value: str | None, *, strict: bool = False) -> str | None:
    if not value:
        return None
    normalized = _TYPES.get(value.strip().casefold())
    if normalized is None and strict:
        raise ValueError(f"Unsupported package type: {value}")
    return normalized


def normalized_package_values(data: dict) -> dict:
    """Add normalized fields without overwriting omitted PATCH fields."""
    result = dict(data)
    parsed_amount, parsed_unit = parse_package(result.get("package_size")) if "package_size" in result else (None, None)
    if "package_amount" not in result and parsed_amount is not None:
        result["package_amount"] = parsed_amount
    if "package_unit" in result:
        result["package_unit"] = normalize_package_unit(result["package_unit"], strict=result["package_unit"] is not None)
    elif parsed_unit is not None:
        result["package_unit"] = parsed_unit
    if "package_type_canonical" in result:
        result["package_type_canonical"] = normalize_package_type(result["package_type_canonical"], strict=result["package_type_canonical"] is not None)
    elif result.get("package_type"):
        result["package_type_canonical"] = normalize_package_type(result["package_type"])
    if "currency" in result:
        result["currency"] = normalize_currency(result["currency"], strict=result["currency"] is not None)
    if "package_size" not in result and result.get("package_amount") is not None and result.get("package_unit"):
        result["package_size"] = format_package(result["package_amount"], result["package_unit"])
    return result
