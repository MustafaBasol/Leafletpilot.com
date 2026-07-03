from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


CURRENCY_SYMBOLS = {
    "€": "EUR",
    "$": "USD",
    "£": "GBP",
    "₺": "TRY",
}
CURRENCY_CODES = {"EUR", "USD", "GBP", "TRY"}
PRICE_NUMBER_RE = r"\d+(?:[.,]\d{1,2})"
PRICE_TOKEN_RE = re.compile(
    rf"(?P<prefix>[€$£₺])?\s*(?P<number>{PRICE_NUMBER_RE})\s*(?P<suffix>[€$£₺]|EUR|USD|GBP|TRY)?",
    re.IGNORECASE,
)
OLD_NEW_RE = re.compile(
    rf"\bold\s+(?P<old>{PRICE_NUMBER_RE})\s*(?:[€$£₺]|EUR|USD|GBP|TRY)?\s+new\s+(?P<new>{PRICE_NUMBER_RE})",
    re.IGNORECASE,
)
SEPARATOR_RE = re.compile(r"\s*(?:->|[-:|]|\t)\s*")
SPACES_RE = re.compile(r"\s+")
PACKAGE_UNIT_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:kg|g|gr|l|lt|ml)\b", re.IGNORECASE)
QUANTITY_RE = re.compile(r"\b\d+\s*(?:x|li|lü|lu|lı|'li|'lü|'lu|'lı)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedCampaignLine:
    raw_line: str
    incoming_name: str
    display_name: str
    price: Decimal | None
    old_price: Decimal | None
    currency: str
    unit_label: str | None
    quantity_label: str | None
    category_hint: str | None
    sort_order: int
    parsed_payload: dict[str, Any] = field(default_factory=dict)


def parse_campaign_text(raw_text: str, default_currency: str = "EUR") -> list[ParsedCampaignLine]:
    """Parse one campaign item per non-empty line with simple deterministic price rules."""
    items: list[ParsedCampaignLine] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        items.append(_parse_line(line, sort_order=len(items), default_currency=default_currency))
    return items


def parse_price(value: str) -> Decimal | None:
    match = PRICE_TOKEN_RE.search(value.strip())
    if match is None:
        return None
    normalized = match.group("number").replace(",", ".")
    try:
        return Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def detect_currency(value: str, default_currency: str = "EUR") -> str:
    upper_value = value.upper()
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in value:
            return code
    for code in CURRENCY_CODES:
        if code in upper_value:
            return code
    return default_currency.upper()


def clean_product_name(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"\bold\b|\bnew\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" -:|\t")
    return SPACES_RE.sub(" ", cleaned).strip()


def _parse_line(line: str, *, sort_order: int, default_currency: str) -> ParsedCampaignLine:
    warnings: list[str] = []
    currency = detect_currency(line, default_currency)
    price: Decimal | None = None
    old_price: Decimal | None = None
    name_part = line
    parser_rule = "no_price"

    old_new_match = OLD_NEW_RE.search(line)
    if old_new_match is not None:
        old_price = parse_price(old_new_match.group("old"))
        price = parse_price(old_new_match.group("new"))
        name_part = line[: old_new_match.start()]
        parser_rule = "old_new_words"
    else:
        price_matches = list(PRICE_TOKEN_RE.finditer(line))
        if len(price_matches) >= 2 and _prices_are_terminal(line, price_matches[-2:]):
            old_price = parse_price(price_matches[-2].group(0))
            price = parse_price(price_matches[-1].group(0))
            name_part = line[: price_matches[-2].start()]
            parser_rule = "terminal_old_new_prices"
        elif price_matches:
            last_match = price_matches[-1]
            price = parse_price(last_match.group(0))
            name_part = line[: last_match.start()]
            parser_rule = _separator_rule(line, last_match)

    if price is None:
        warnings.append("no_price_found")
        name_part = line

    incoming_name = clean_product_name(name_part)
    if not incoming_name:
        incoming_name = clean_product_name(SEPARATOR_RE.split(line, maxsplit=1)[0]) or line
        warnings.append("missing_product_name")

    parsed_payload: dict[str, Any] = {
        "parser": "deterministic_text_v1",
        "rule": parser_rule,
        "warnings": warnings,
    }

    return ParsedCampaignLine(
        raw_line=line,
        incoming_name=incoming_name,
        display_name=incoming_name,
        price=price,
        old_price=old_price,
        currency=currency,
        unit_label=_first_match(PACKAGE_UNIT_RE, incoming_name),
        quantity_label=_first_match(QUANTITY_RE, incoming_name),
        category_hint=None,
        sort_order=sort_order,
        parsed_payload=parsed_payload,
    )


def _separator_rule(line: str, price_match: re.Match[str]) -> str:
    before_price = line[: price_match.start()]
    if "\t" in before_price:
        return "tab_separator"
    if "|" in before_price:
        return "pipe_separator"
    if ":" in before_price:
        return "colon_separator"
    if "-" in before_price:
        return "dash_separator"
    return "terminal_price"


def _prices_are_terminal(line: str, matches: list[re.Match[str]]) -> bool:
    between = line[matches[0].end() : matches[1].start()]
    after = line[matches[1].end() :]
    return not after.strip() and not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", between)


def _first_match(pattern: re.Pattern[str], value: str) -> str | None:
    match = pattern.search(value)
    return match.group(0) if match is not None else None
