from datetime import UTC, datetime

from app.services.preview_renderer import _apply_campaign_intelligence, render_render_payload_html


def test_reduced_emphasis_override_wins_over_intelligence_recommendation() -> None:
    items = [{"id": "one", "name": "Cola"}, {"id": "two", "name": "Cips"}]
    config = {
        "reduced_emphasis_item_ids": ["one"],
        "campaign_intelligence": {
            "engineVersion": "campaign-intelligence-v1",
            "strategy": {"composition": "hero_plus_grid"},
            "products": [
                {"productId": "one", "role": "hero", "recommendedSize": "xl"},
                {"productId": "two", "role": "standard", "recommendedSize": "md"},
            ],
        },
    }

    ordered, roles, _ = _apply_campaign_intelligence(items, config)

    assert roles[0] == "support"
    assert ordered[0]["_merchandising"]["image_treatment"] == "medium"


def test_price_and_headline_prominence_are_bounded_renderer_inputs() -> None:
    html = render_render_payload_html(
        {
            "contract_version": 2,
            "template_slug": "promo-4",
            "template_config": {"price_prominence": "high", "headline_emphasis": "high"},
            "title": "Hafta Sonu",
            "items": [
                {"id": "one", "name": "Cola", "price": "2.49", "currency": "EUR"},
                {"id": "two", "name": "Cips", "price": "1.29", "currency": "EUR"},
            ],
        },
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    assert "font-size:50px" in html
    assert "font-size:41px" in html
