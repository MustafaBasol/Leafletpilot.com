"""Constrained flyer presets sharing one retail-promo visual language."""

FLYER_PRESETS = {
    4: {"slug": "promo-4", "name": "Promo 4", "columns": 2, "rows": 2},
    6: {"slug": "promo-6", "name": "Promo 6", "columns": 2, "rows": 3},
    9: {"slug": "promo-9", "name": "Promo 9", "columns": 3, "rows": 3},
    12: {"slug": "promo-12", "name": "Promo 12", "columns": 3, "rows": 4},
    16: {"slug": "promo-16", "name": "Promo 16", "columns": 4, "rows": 4},
}


def preset_for_config(config: dict | None) -> dict | None:
    if not isinstance(config, dict):
        return None
    try:
        return FLYER_PRESETS.get(int(config.get("slot_count")))
    except (TypeError, ValueError):
        return None
