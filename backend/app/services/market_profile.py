"""Canonical market identity projection for brochure rendering and freezing."""
from __future__ import annotations

from typing import Any


def market_brochure_profile(market: Any) -> dict[str, Any]:
    """Expose only fields explicitly enabled for brochure output."""
    visibility = {
        "logo": bool(getattr(market, "brochure_show_logo", True)),
        "address": bool(getattr(market, "brochure_show_address", False)),
        "phone": bool(getattr(market, "brochure_show_phone", False)),
        "website": bool(getattr(market, "brochure_show_website", False)),
        "instagram": bool(getattr(market, "brochure_show_instagram", False)),
        "facebook": bool(getattr(market, "brochure_show_facebook", False)),
    }
    address = ", ".join(
        str(value).strip()
        for value in (
            getattr(market, "address_line_1", None), getattr(market, "address_line_2", None),
            getattr(market, "postal_code", None), getattr(market, "city", None),
            getattr(market, "country_code", None),
        )
        if value
    )
    profile: dict[str, Any] = {
        "name": getattr(market, "name", None),
        "visibility": visibility,
        "logo_key": getattr(market, "logo_storage_key", None) if visibility["logo"] else None,
        "logo_mime_type": getattr(market, "logo_mime_type", None) if visibility["logo"] else None,
    }
    raw_values = {
        "address": address, "phone": getattr(market, "contact_phone", None),
        "website": getattr(market, "website_url", None), "instagram": getattr(market, "instagram_url", None),
        "facebook": getattr(market, "facebook_url", None),
    }
    for key, value in raw_values.items():
        if visibility[key] and value:
            profile[key] = str(value).strip()
    return profile


def profile_footer_lines(profile: dict[str, Any] | None) -> list[str]:
    profile = profile or {}
    labels = {"address": "Adres", "phone": "Tel", "website": "Web", "instagram": "Instagram", "facebook": "Facebook"}
    return [f"{labels[key]}: {profile[key]}" for key in labels if profile.get(key)]