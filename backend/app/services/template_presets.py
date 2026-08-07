"""Constrained flyer presets sharing one retail-promo visual language."""

from typing import Any

FLYER_PRESETS = {
    4: {"slug": "promo-4", "name": "Promo 4", "columns": 2, "rows": 2},
    6: {"slug": "promo-6", "name": "Promo 6", "columns": 2, "rows": 3},
    9: {"slug": "promo-9", "name": "Promo 9", "columns": 3, "rows": 3},
    12: {"slug": "promo-12", "name": "Promo 12", "columns": 3, "rows": 4},
    16: {"slug": "promo-16", "name": "Promo 16", "columns": 4, "rows": 4},
}

SUPERMARKET_PRESETS = {
    4: {"slug": "supermarket-promo-4", "name": "Supermarket Promo 4", "columns": 2, "rows": 2, "family": "supermarket"},
    9: {"slug": "supermarket-promo-9", "name": "Supermarket Promo 9", "columns": 3, "rows": 3, "family": "supermarket"},
    16: {"slug": "supermarket-promo-16", "name": "Supermarket Promo 16", "columns": 4, "rows": 4, "family": "supermarket"},
}

SUPERMARKET_VISUAL_DEFAULTS = {
    "background_start": "#ef3b24", "background_end": "#a40e1a", "card_background": "#fff8e7",
    "card_border_color": "#f1b900", "price_panel_background": "#ffd928", "price_color": "#c5161d",
    "title_color": "#ffffff", "product_title_color": "#2b1a12",
    "brand_label_background": "#c5161d", "brand_label_color": "#ffffff", "header_style": "burst",
    "card_style": "shadow", "price_style": "panel", "badge_style": "sticker", "image_treatment": "stage",
    "show_payment_icons": True, "show_additional_logos": True, "show_stock_message": True, "show_footer_note": True,
    "show_header_title": True, "show_market_name": True, "show_old_price": True,
    "show_discount_badge": True, "show_product_image": True, "show_product_name": True,
    "show_package_size": True, "show_footer": True,
}

SUPERMARKET_STYLE_OPTIONS = {
    "header_style": ("burst", "band", "minimal"),
    "card_style": ("shadow", "outlined", "rounded"),
    "price_style": ("panel", "ticket", "split"),
    "badge_style": ("pill", "sticker", "burst", "ribbon"),
    "image_treatment": ("stage", "cutout", "photo"),
}

# Page-composition budgets are explicit per family so 4/9/16 are not scaled
# copies. Values are consumed as CSS variables by the one shared renderer.
SUPERMARKET_DENSITY_PROFILES = {
    "supermarket-promo-4": {
        "name": "editorial", "header_height": 226, "grid_height": 1390, "grid_gap": 18,
        "card_padding": 15, "card_radius": 20, "image_height": 420, "name_size": 23,
        "name_lines": 2, "unit_size": 15, "price_size": 50, "price_panel_height": 92,
        "badge_size": 12, "footer_height": 38,
    },
    "supermarket-promo-9": {
        "name": "weekly", "header_height": 204, "grid_height": 1404, "grid_gap": 12,
        "card_padding": 10, "card_radius": 15, "image_height": 240, "name_size": 17,
        "name_lines": 2, "unit_size": 13, "price_size": 35, "price_panel_height": 72,
        "badge_size": 10, "footer_height": 36,
    },
    "supermarket-promo-16": {
        "name": "compact", "header_height": 174, "grid_height": 1432, "grid_gap": 8,
        "card_padding": 7, "card_radius": 11, "image_height": 172, "name_size": 14,
        "name_lines": 2, "unit_size": 11, "price_size": 27, "price_panel_height": 58,
        "badge_size": 9, "footer_height": 32,
    },
}

_COLOR_KEYS = {
    "background_start", "background_end", "card_background", "card_border_color",
    "price_panel_background", "price_color", "title_color", "product_title_color",
    "brand_label_background", "brand_label_color",
}


def supermarket_visual_config(value: dict[str, Any] | None) -> dict[str, Any]:
    """Return safe semantic tokens, preserving legacy generic color controls."""
    source = dict(value or {})
    resolved = dict(SUPERMARKET_VISUAL_DEFAULTS)
    if "background_start" not in source and source.get("primary_color"):
        source["background_start"] = source["primary_color"]
    if "background_end" not in source and source.get("secondary_color"):
        source["background_end"] = source["secondary_color"]
    for key in _COLOR_KEYS:
        candidate = source.get(key)
        if isinstance(candidate, str) and len(candidate) == 7 and candidate.startswith("#"):
            try:
                int(candidate[1:], 16)
            except ValueError:
                continue
            resolved[key] = candidate.lower()
    for key, options in SUPERMARKET_STYLE_OPTIONS.items():
        candidate = source.get(key)
        legacy = {"bold": "panel", "compact": "split", "square": "sticker"}.get(candidate, candidate)
        if legacy in options:
            resolved[key] = legacy
    for key in (
        "show_payment_icons", "show_additional_logos", "show_stock_message", "show_footer_note",
        "show_header_title", "show_market_name", "show_old_price", "show_discount_badge",
        "show_product_image", "show_product_name", "show_package_size", "show_footer",
    ):
        if key in source:
            resolved[key] = bool(source[key])
    return resolved


def supermarket_density_profile(slug: str) -> dict[str, Any]:
    return dict(SUPERMARKET_DENSITY_PROFILES.get(slug, SUPERMARKET_DENSITY_PROFILES["supermarket-promo-4"]))


def preset_for_config(config: dict | None) -> dict | None:
    if not isinstance(config, dict):
        return None
    try:
        return FLYER_PRESETS.get(int(config.get("slot_count")))
    except (TypeError, ValueError):
        return None
