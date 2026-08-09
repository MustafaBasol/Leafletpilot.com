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
    assert ordered[0]["_merchandising"]["image_treatment"] == "compact"


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


def test_explicit_hero_gets_dominant_renderer_weight() -> None:
    items = [
        {"id": "one", "name": "Cola", "price": "2.49", "currency": "EUR", "is_hero": True},
        {"id": "two", "name": "Cips", "price": "1.29", "currency": "EUR"},
        {"id": "three", "name": "Sut", "price": "0.99", "currency": "EUR"},
    ]
    builder_config = {
        "hero_treatment": "strong",
        "campaign_intelligence": {
            "engineVersion": "campaign-intelligence-v1",
            "strategy": {"composition": "hero_plus_grid"},
            "products": [
                {"productId": "two", "role": "hero", "recommendedSize": "md"},
                {"productId": "one", "role": "standard", "recommendedSize": "md"},
                {"productId": "three", "role": "standard", "recommendedSize": "md"},
            ],
        },
    }

    ordered, _, strategy = _apply_campaign_intelligence(items, builder_config)
    html = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-4",
            "builder_config": builder_config,
            "items": ordered,
            "intelligence_strategy": strategy,
        },
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    assert ordered[0]["id"] == "one"
    assert ordered[0]["_merchandising"]["visual_weight"] == "dominant"
    assert ordered[0]["_merchandising"]["image_treatment"] == "hero"
    assert 'data-smart-role="hero"' in html
    assert 'data-visual-weight="dominant"' in html
    assert 'data-price-treatment="hero-panel"' in html
    assert 'data-refinement-strategy="hero-trio"' in html


def test_simpler_and_eye_catching_are_distinct_render_strategies() -> None:
    items = [
        {"id": str(index), "name": f"Product {index}", "price": "1.99", "currency": "EUR"}
        for index in range(6)
    ]
    simple_config = {
        "visual_density": "simple",
        "layout_strategy": "simplified_grid",
        "header_style": "minimal",
        "card_style": "outlined",
        "show_discount_badge": False,
        "show_footer": False,
    }
    eye_config = {
        "visual_density": "expressive",
        "layout_strategy": "hero_focused",
        "header_style": "burst",
        "card_style": "shadow",
        "badge_style": "burst",
        "headline_emphasis": "high",
        "price_prominence": "high",
        "smart_composition": True,
    }

    simple = render_render_payload_html(
        {"template_slug": "supermarket-promo-9", "template_config": simple_config, "builder_config": simple_config, "items": items},
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    eye_catching = render_render_payload_html(
        {"template_slug": "supermarket-promo-9", "template_config": eye_config, "builder_config": eye_config, "items": items},
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    assert 'data-visual-mode="simple"' in simple
    assert "composition-weekly-grid" in simple
    assert "retail-header-minimal" in simple
    assert 'data-visual-mode="eye-catching"' in eye_catching
    assert "price-prominence-high" in eye_catching
    assert "headline-emphasis-high" in eye_catching
    assert 'data-smart-role="hero"' in eye_catching
    assert simple != eye_catching
