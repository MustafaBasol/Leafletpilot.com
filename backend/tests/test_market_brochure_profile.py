from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.market import MarketSettingsUpdate
from app.services.ai.brochure_validation import _required_facts
from app.services.ai.professionalization import frozen_snapshot_hash, immutable_brochure_facts
from app.services.market_profile import market_brochure_profile, profile_footer_lines
from app.services.preview_renderer import render_render_payload_html


def market(**overrides):
    data = {
        "name": "Vatan Market", "logo_storage_key": "markets/vatan/logo.png", "logo_mime_type": "image/png",
        "address_line_1": "Ataturk Cad. 1", "address_line_2": None, "postal_code": "75001", "city": "Paris",
        "country_code": "FR", "contact_phone": "+33 1 23 45 67 89", "website_url": "https://vatan.example",
        "instagram_url": "@vatanmarket", "facebook_url": "https://facebook.com/vatanmarket",
        "brochure_show_logo": True, "brochure_show_address": False, "brochure_show_phone": False,
        "brochure_show_website": False, "brochure_show_instagram": False, "brochure_show_facebook": False,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_profile_defaults_keep_optional_contact_data_private():
    profile = market_brochure_profile(market())
    assert profile["name"] == "Vatan Market"
    assert profile["logo_key"] == "markets/vatan/logo.png"
    assert profile["visibility"]["logo"] is True
    assert not {"address", "phone", "website", "instagram", "facebook"}.intersection(profile)


def test_profile_exposes_only_enabled_values_and_renderer_places_them_in_footer():
    profile = market_brochure_profile(market(brochure_show_address=True, brochure_show_instagram=True))
    assert profile["address"] == "Ataturk Cad. 1, 75001, Paris, FR"
    assert profile["instagram"] == "@vatanmarket"
    assert "phone" not in profile
    payload = {
        "template_slug": "promo-4", "template_config": {}, "market_name": profile["name"], "market_profile": profile,
        "footer_contacts": profile_footer_lines(profile), "header": {}, "title": "Haftanin Firsatlari", "language": "tr", "items": [],
    }
    html = render_render_payload_html(payload, generated_at=__import__("datetime").datetime.now())
    assert "Adres: Ataturk Cad. 1" in html
    assert "Instagram: @vatanmarket" in html
    assert "+33 1 23 45 67 89" not in html


def test_settings_validation_preserves_canonical_name_and_urls():
    update = MarketSettingsUpdate(name="  Yeni Market  ", website_url="https://new.example", instagram_url="@newmarket")
    assert update.name == "Yeni Market"
    assert update.website_url == "https://new.example"
    with pytest.raises(ValidationError):
        MarketSettingsUpdate(name="   ")
    with pytest.raises(ValidationError):
        MarketSettingsUpdate(website_url="new.example")
    with pytest.raises(ValidationError):
        MarketSettingsUpdate(phone="call-me")


def test_frozen_ai_facts_include_only_enabled_market_fields_and_change_snapshot_hash():
    snapshot = {
        "market_name": "Vatan Market", "title": "Haftanin Firsatlari", "header": {}, "items": [],
        "market_profile": {
            "name": "Vatan Market", "logo_key": "frozen-logo.png",
            "visibility": {"logo": True, "address": True, "phone": False, "website": False, "instagram": True, "facebook": False},
            "address": "Frozen address", "phone": "Hidden phone", "instagram": "@frozen",
        },
    }
    facts = immutable_brochure_facts(snapshot)
    assert facts["market"] == {"name": "Vatan Market", "address": "Frozen address", "instagram": "@frozen", "logo_reference": "frozen-logo.png"}
    assert "Hidden phone" not in str(facts)
    original_hash = frozen_snapshot_hash(snapshot)
    snapshot["market_profile"]["address"] = "Changed address"
    assert frozen_snapshot_hash(snapshot) != original_hash


def test_validation_requires_enabled_profile_facts_but_not_disabled_values():
    snapshot = {
        "market_name": "Vatan Market", "title": "Hafta", "header": {}, "items": [],
        "market_profile": {"name": "Vatan Market", "visibility": {"address": True, "phone": False}, "address": "Frozen address", "phone": "Private phone"},
    }
    required = _required_facts(snapshot)
    assert "Frozen address" in required
    assert "Private phone" not in required
