from datetime import UTC, datetime

import pytest

from app.services.preview_renderer import render_render_payload_html
from app.services.template_presets import SUPERMARKET_PRESETS, SUPERMARKET_VISUAL_DEFAULTS


@pytest.mark.parametrize(("slug", "columns", "rows", "count"), [
    ("supermarket-promo-4", 2, 2, 4),
    ("supermarket-promo-9", 3, 3, 9),
    ("supermarket-promo-16", 4, 4, 16),
])
def test_supermarket_layouts_render_explicit_grids(slug, columns, rows, count):
    payload = {"template_slug": slug, "title": "Weekly deals", "items": [
        {"name": "Long product name " * 3 if i == 0 else f"Product {i}", "brand": "Brand", "price": "999999.99" if i == 1 else "1.99", "old_price": "2.49", "currency": "EUR", "quantity_label": "2 x 500g"}
        for i in range(count)
    ]}
    html = render_render_payload_html(payload, generated_at=datetime.now(UTC))
    assert f"preview-{slug}" in html
    assert f"grid-template-columns:repeat({columns}" in html
    assert f"grid-template-rows:repeat({rows}" in html
    assert html.count('class="product-card"') == count
    assert html.count('class="price-panel"') == count
    assert 'class="price-minor"' in html
    assert 'class="product-unit"' in html


def test_supermarket_defaults_and_header_assets_are_available():
    assert {v["slug"] for v in SUPERMARKET_PRESETS.values()} == {"supermarket-promo-4", "supermarket-promo-9", "supermarket-promo-16"}
    assert SUPERMARKET_VISUAL_DEFAULTS["price_panel_background"] == "#ffd928"
    html = render_render_payload_html({"template_slug": "supermarket-promo-4", "title": "Offers", "header": {"market_logo": "missing.svg", "header_logos": ["a.svg", "b.svg"], "payment_icons": ["card.svg"], "validity_text": "01-07 July 2026", "stock_message": "While stocks last"}, "items": [{"name": "Milk", "brand": "Fresh", "price": "1.99", "currency": "EUR", "quantity_label": "1L"}]}, generated_at=datetime.now(UTC))
    assert "PROMO" in html and "01-07 July 2026" in html and "While stocks last" in html
    assert "price-panel" in html and "background:#ffd928" in html
    assert "image-placeholder" in html


def test_supermarket_rejects_overflow_without_affecting_generic():
    adaptive = render_render_payload_html({"template_slug": "supermarket-promo-4", "items": [{"name": "x"}] * 5}, generated_at=datetime.now(UTC))
    assert "preview-supermarket-promo-9" in adaptive
    assert "grid-template-columns:repeat(3" in adaptive
    generic = render_render_payload_html({"template_slug": "promo-4", "items": [{"name": "x"}]}, generated_at=datetime.now(UTC))
    assert "price-panel" not in generic


@pytest.mark.parametrize("currency", ["EUR", "TRY", "USD", "GBP", "CHF", "kr"])
def test_supermarket_currency_encoding_and_price_parts(currency):
    html = render_render_payload_html({"template_slug": "supermarket-promo-4", "items": [{"name": "Milk", "price": "12.99", "currency": currency}]}, generated_at=datetime.now(UTC))
    expected = {"EUR": "€", "TRY": "₺", "USD": "$", "GBP": "£", "CHF": "CHF", "kr": "kr"}[currency]
    assert '<meta charset="utf-8">' in html
    assert expected in html
    assert "Ã¢â€šÂ¬" not in html
    assert "�" not in html
    assert 'class="price-major"' in html and 'class="price-minor"' in html


@pytest.mark.parametrize("value,currency,major,minor", [("1.99", "EUR", "1", ",99"), ("12.99", "USD", "12", ".99"), ("999999.99", "CHF", "999999", ".99"), ("199", "TRY", "199", ",00")])
def test_supermarket_currency_formats_are_safe(value, currency, major, minor):
    html = render_render_payload_html({"template_slug": "supermarket-promo-4", "items": [{"name": "x", "price": value, "currency": currency}]}, generated_at=datetime.now(UTC))
    assert f'<span class="price-major">{major}</span>' in html
    assert f'<span class="price-minor">{minor}</span>' in html
