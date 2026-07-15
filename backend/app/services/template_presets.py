"""Constrained flyer presets sharing one retail-promo visual language."""

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
    "price_panel_background": "#ffd928", "price_color": "#c5161d", "title_color": "#ffffff",
    "brand_label_background": "#c5161d", "brand_label_color": "#ffffff", "header_style": "burst",
    "show_payment_icons": True, "show_additional_logos": True, "show_stock_message": True, "show_footer_note": True,
}


def preset_for_config(config: dict | None) -> dict | None:
    if not isinstance(config, dict):
        return None
    try:
        return FLYER_PRESETS.get(int(config.get("slot_count")))
    except (TypeError, ValueError):
        return None
