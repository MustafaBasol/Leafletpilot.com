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
        "name": "editorial", "composition": "hero-offers", "header_height": 150,
        "grid_height": 1474, "grid_gap": 20, "card_padding": 14, "card_radius": 18,
        "image_height": 286, "name_size": 24, "name_lines": 2, "unit_size": 15,
        "price_size": 50, "price_panel_height": 90, "badge_size": 16, "footer_height": 38,
    },
    "supermarket-promo-9": {
        "name": "weekly", "composition": "weekly-grid", "header_height": 140,
        "grid_height": 1486, "grid_gap": 12, "card_padding": 9, "card_radius": 12,
        "image_height": 238, "name_size": 18, "name_lines": 2, "unit_size": 13,
        "price_size": 38, "price_panel_height": 82, "badge_size": 12, "footer_height": 36,
    },
    "supermarket-promo-16": {
        "name": "compact", "composition": "catalogue-grid", "header_height": 122,
        "grid_height": 1510, "grid_gap": 8, "card_padding": 6, "card_radius": 8,
        "image_height": 174, "name_size": 14, "name_lines": 2, "unit_size": 10,
        "price_size": 28, "price_panel_height": 62, "badge_size": 10, "footer_height": 32,
    },
}

_COLOR_KEYS = {
    "background_start", "background_end", "card_background", "card_border_color",
    "price_panel_background", "price_color", "title_color", "product_title_color",
    "brand_label_background", "brand_label_color",
}

_MIN_TEXT_CONTRAST_RATIO = 4.5


def _srgb_channel_to_linear(channel: int) -> float:
    value = channel / 255.0
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    lr, lg, lb = (_srgb_channel_to_linear(c) for c in (r, g, b))
    return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG relative-luminance contrast ratio between two `#rrggbb` colors."""
    la, lb = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def readable_text_color(background_hex: str, requested_hex: str, *, minimum: float = _MIN_TEXT_CONTRAST_RATIO) -> str:
    """Keep `requested_hex` if it reads clearly on `background_hex`, else fall back to black/white.

    Product-name/unit text is rendered in a single market-configurable color
    with no guarantee it was chosen against the background it actually ends
    up on (Phase 31: production markets left at defaults still hit this via
    composition-specific overrides bleeding into unrelated layouts). Rather
    than trust the configured value blindly, verify it here and substitute
    whichever of pure black/white contrasts better with the background.
    """
    if contrast_ratio(background_hex, requested_hex) >= minimum:
        return requested_hex
    return "#000000" if contrast_ratio(background_hex, "#000000") >= contrast_ratio(background_hex, "#ffffff") else "#ffffff"


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
    resolved["product_title_color"] = readable_text_color(resolved["card_background"], resolved["product_title_color"])
    return resolved


def supermarket_density_profile(slug: str) -> dict[str, Any]:
    return dict(SUPERMARKET_DENSITY_PROFILES.get(slug, SUPERMARKET_DENSITY_PROFILES["supermarket-promo-4"]))


# Internal, gate-owned refinement lever (Phase 28B). Never read or set by
# user-facing code (edit intents, template config API) - the visual quality
# gate is the only writer, and only for a single extra render pass.
FILL_BOOST_CONFIG_KEY = "_quality_gate_fill_boost"

_FILL_BOOST_SCALES = {
    "image_height": 1.10,
    "grid_gap": 0.85,
    "card_padding": 0.85,
    "price_panel_height": 1.08,
}


def apply_density_fill_boost(density: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded, one-shot copy of density with page-fill knobs nudged."""
    boosted = dict(density)
    for key, scale in _FILL_BOOST_SCALES.items():
        if key in boosted:
            boosted[key] = round(boosted[key] * scale)
    return boosted


def preset_for_config(config: dict | None) -> dict | None:
    if not isinstance(config, dict):
        return None
    try:
        return FLYER_PRESETS.get(int(config.get("slot_count")))
    except (TypeError, ValueError):
        return None
