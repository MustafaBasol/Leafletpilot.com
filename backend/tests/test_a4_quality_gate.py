from datetime import datetime, UTC

import pytest

from app.services.preview_renderer import render_render_payload_html


@pytest.mark.parametrize(("slug", "count"), [("promo-4", 4), ("promo-9", 9), ("promo-16", 16)])
def test_a4_layout_has_explicit_grid_and_cards(slug, count):
    payload = {"contract_version": 2, "template_slug": slug, "title": "Offers", "items": [{"name": f"Product {i}", "price": "1.99", "currency": "EUR"} for i in range(count)]}
    html = render_render_payload_html(payload, generated_at=datetime.now(UTC))
    assert f"grid-template-columns:repeat({2 if count == 4 else 3 if count == 9 else 4}" in html
    assert html.count('class="product-card"') == count
    assert "grid-template-rows:repeat" in html
    assert "width:1240px;height:1754px" in html


def test_a4_rejects_implicit_overflow():
    payload = {"contract_version": 2, "template_slug": "promo-4", "items": [{"name": "x"} for _ in range(5)]}
    with pytest.raises(ValueError):
        render_render_payload_html(payload, generated_at=datetime.now(UTC))


def test_a4_card_contains_safe_long_text_and_fallback():
    payload = {"contract_version": 2, "template_slug": "promo-4", "items": [{"name": "A" * 300, "brand": "B" * 300, "price": "999999.99", "currency": "EUR"}]}
    html = render_render_payload_html(payload, generated_at=datetime.now(UTC))
    assert "overflow-wrap:anywhere" in html
    assert "image-placeholder" in html
