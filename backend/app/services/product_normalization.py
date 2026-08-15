"""Small, deterministic normalizers for product catalogue input.

The display fields remain additive compatibility fields; callers can safely send
the historical ``package_size`` / ``package_type`` values during rollout.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_PACKAGE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(ml|cl|l|g|kg|mg|adet|pcs?|pack)\b", re.I)
_UNITS = {"ml": "ml", "cl": "cl", "l": "L", "g": "g", "kg": "kg", "mg": "mg", "adet": "adet", "pc": "adet", "pcs": "adet", "pack": "paket"}
_TYPES = {"bottle": "şişe", "şişe": "şişe", "can": "kutu", "kutu": "kutu", "box": "kutu", "bag": "poşet", "poşet": "poşet", "jar": "kavanoz", "kavanoz": "kavanoz", "packet": "paket", "paket": "paket"}


def normalize_currency(value: str | None, default: str = "EUR") -> str:
    value = (value or default).strip().upper()
    return value if value in {"EUR", "TRY", "USD", "GBP"} else default


def parse_package(value: str | None, unit: str | None = None) -> tuple[Decimal | None, str | None]:
    if value:
        match = _PACKAGE.match(value)
        if match:
            try:
                return Decimal(match.group(1).replace(",", ".")), _UNITS[match.group(2).lower()]
            except (InvalidOperation, KeyError):
                pass
    return None, (_UNITS.get((unit or "").strip().lower()) or unit)


def format_package(amount: Decimal | None, unit: str | None, fallback: str | None = None) -> str | None:
    if amount is None or not unit:
        return fallback
    text = format(amount.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text} {unit}"


def normalize_package_type(value: str | None) -> str | None:
    if not value:
        return None
    return _TYPES.get(value.strip().casefold(), value.strip().casefold())


def normalized_package_values(data: dict) -> dict:
    """Fill additive canonical package fields without changing legacy display input."""
    result = dict(data)
    amount, unit = parse_package(result.get("package_size"), result.get("package_unit"))
    if result.get("package_amount") is None:
        result["package_amount"] = amount
    if not result.get("package_unit"):
        result["package_unit"] = unit
    result["package_type_canonical"] = normalize_package_type(result.get("package_type_canonical") or result.get("package_type"))
    result["currency"] = normalize_currency(result.get("currency"))
    return result
