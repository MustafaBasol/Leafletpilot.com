import re
from datetime import UTC, datetime

import pytest

from app.services.preview_renderer import render_render_payload_html
from app.services.template_presets import (
    SUPERMARKET_DENSITY_PROFILES,
    SUPERMARKET_PRESETS,
    SUPERMARKET_VISUAL_DEFAULTS,
)


@pytest.mark.parametrize(
    ("slug", "columns", "rows", "count", "density"),
    [
        ("supermarket-promo-4", 2, 2, 4, "editorial"),
        ("supermarket-promo-9", 3, 3, 9, "weekly"),
        ("supermarket-promo-16", 4, 4, 16, "compact"),
    ],
)
def test_supermarket_layouts_render_explicit_grids(slug, columns, rows, count, density):
    payload = {
        "template_slug": slug,
        "title": "Weekly deals",
        "items": [
            {
                "name": "Long product name " * 3 if i == 0 else f"Product {i}",
                "brand": "Brand",
                "price": "999999.99" if i == 1 else "1.99",
                "old_price": "2.49",
                "currency": "EUR",
                "quantity_label": "2 x 500g",
            }
            for i in range(count)
        ],
    }
    html = render_render_payload_html(payload, generated_at=datetime.now(UTC))
    assert f"preview-{slug}" in html
    assert f"grid-template-columns:repeat({columns}" in html
    assert f"grid-template-rows:repeat({rows}" in html
    assert f'data-density-profile="{density}"' in html
    assert f'data-layout="{columns}x{rows}"' in html
    assert f"density-{density}" in html
    assert html.count('class="product-card"') == count
    assert html.count('class="price-panel"') == count
    assert html.count('class="promo-card-image"') == count
    assert 'class="price-minor"' in html
    assert 'class="product-unit"' in html
    assert "object-fit:contain" in html
    assert 'grid-template-areas:"price badge" "price old"' in html
    first_card = html.index('<article class="product-card"')
    assert first_card < html.index('class="promo-card-image"', first_card)
    assert html.index('class="promo-card-image"', first_card) < html.index(
        'class="price-panel"', first_card
    )
    assert html.index('class="price-panel"', first_card) < html.index(
        'class="brand-label"', first_card
    )
    assert html.index('class="brand-label"', first_card) < html.index(
        'class="product-name"', first_card
    )


@pytest.mark.parametrize(
    ("slug", "count"),
    [
        ("supermarket-promo-4", 4),
        ("supermarket-promo-9", 9),
        ("supermarket-promo-16", 16),
    ],
)
def test_smart_composition_plan_drives_shared_renderer_without_changing_manual_default(slug, count):
    items = [
        {
            "id": f"item-{index}",
            "name": f"Offer {index}",
            "category": f"category-{index % 4}",
            "brand": f"brand-{index % 5}",
            "image_key": None if index == count - 1 else f"missing-{index}.png",
            "price": str(index + 1),
            "old_price": str(index + 5),
            "sort_order": index,
        }
        for index in range(count)
    ]
    payload = {
        "campaign_id": "stable-campaign",
        "template_slug": slug,
        "builder_config": {"smart_composition": True},
        "items": items,
    }
    html = render_render_payload_html(payload, generated_at=datetime(2026, 8, 9, tzinfo=UTC))
    assert html == render_render_payload_html(
        payload, generated_at=datetime(2026, 8, 9, tzinfo=UTC)
    )
    assert "smart-composition" in html and "smart-strategy-" in html
    assert len(re.findall(r'<article[^>]+data-smart-role="hero"', html)) == 1
    assert (
        len(re.findall(r'<article[^>]+data-smart-role="featured"', html))
        == {4: 1, 9: 3, 16: 4}[count]
    )
    assert 'data-price-treatment="promo-panel"' in html
    assert 'grid-template-areas:"price badge" "price old"' in html
    first_card = html.index('<article class="product-card"')
    assert first_card < html.index('class="promo-card-image"', first_card)
    assert html.index('class="promo-card-image"', first_card) < html.index(
        'class="price-panel"', first_card
    )
    assert html.index('class="price-panel"', first_card) < html.index(
        'class="brand-label"', first_card
    )
    assert html.index('class="brand-label"', first_card) < html.index(
        'class="product-name"', first_card
    )


def test_supermarket_defaults_and_header_assets_are_available():
    assert {v["slug"] for v in SUPERMARKET_PRESETS.values()} == {
        "supermarket-promo-4",
        "supermarket-promo-9",
        "supermarket-promo-16",
    }
    assert SUPERMARKET_VISUAL_DEFAULTS["price_panel_background"] == "#ffd928"
    html = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-4",
            "title": "Offers",
            "header": {
                "market_logo": "missing.svg",
                "header_logos": ["a.svg", "b.svg"],
                "payment_icons": ["card.svg"],
                "validity_text": "01-07 July 2026",
                "stock_message": "While stocks last",
            },
            "items": [
                {
                    "name": "Milk",
                    "brand": "Fresh",
                    "price": "1.99",
                    "currency": "EUR",
                    "quantity_label": "1L",
                }
            ],
        },
        generated_at=datetime.now(UTC),
    )
    assert "PROMO" in html and "01-07 July 2026" in html and "While stocks last" in html
    assert "price-panel" in html and "background:#ffd928" in html
    assert "image-placeholder" in html


def test_density_profiles_are_explicit_and_materially_distinct():
    editorial = SUPERMARKET_DENSITY_PROFILES["supermarket-promo-4"]
    weekly = SUPERMARKET_DENSITY_PROFILES["supermarket-promo-9"]
    compact = SUPERMARKET_DENSITY_PROFILES["supermarket-promo-16"]
    assert editorial["image_height"] > weekly["image_height"] > compact["image_height"]
    assert editorial["price_size"] > weekly["price_size"] > compact["price_size"]
    assert editorial["grid_gap"] > weekly["grid_gap"] > compact["grid_gap"]
    assert {editorial["name"], weekly["name"], compact["name"]} == {
        "editorial",
        "weekly",
        "compact",
    }


def test_semantic_visual_tokens_and_variants_are_constrained():
    html = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-4",
            "template_config": {
                "background_start": "#123456",
                "background_end": "#234567",
                "card_background": "#fefefe",
                "card_border_color": "#abcdef",
                "price_panel_background": "#fedcba",
                "price_color": "#654321",
                "header_style": "band",
                "card_style": "outlined",
                "price_style": "ticket",
                "badge_style": "ribbon",
                "image_treatment": "cutout",
            },
            "items": [{"name": "Milk", "price": "1.99", "badge": "SAVE", "currency": "EUR"}],
        },
        generated_at=datetime.now(UTC),
    )
    assert (
        "retail-header-band retail-card-outlined retail-price-ticket retail-badge-ribbon retail-image-cutout"
        in html
    )
    for color in ("#123456", "#234567", "#fefefe", "#abcdef", "#fedcba", "#654321"):
        assert color in html

    unsafe = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-4",
            "template_config": {"background_start": "red;position:fixed", "badge_style": "evil"},
            "items": [],
        },
        generated_at=datetime.now(UTC),
    )
    assert "red;position:fixed" not in unsafe
    assert "retail-badge-sticker" in unsafe


def test_supermarket_visibility_controls_affect_real_output():
    html = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-4",
            "template_config": {
                "show_product_image": False,
                "show_product_name": False,
                "show_package_size": False,
                "show_old_price": False,
                "show_discount_badge": False,
                "show_footer": False,
                "show_stock_message": False,
            },
            "header": {"stock_message": "Hidden stock"},
            "items": [{"name": "Hidden", "price": "1.99", "old_price": "2.49", "badge": "SAVE"}],
        },
        generated_at=datetime.now(UTC),
    )
    for hidden in (
        '<div class="promo-card-image">',
        '<h2 class="product-name"',
        '<p class="product-unit"',
        '<span class="old-price">',
        '<span class="promo-badge">',
        "Hidden stock",
        '<footer class="footer">',
    ):
        assert hidden not in html
    assert "price-panel" in html


def test_supermarket_rejects_overflow_without_affecting_generic():
    adaptive = render_render_payload_html(
        {"template_slug": "supermarket-promo-4", "items": [{"name": "x"}] * 5},
        generated_at=datetime.now(UTC),
    )
    assert "preview-supermarket-promo-9" in adaptive
    assert "grid-template-columns:repeat(3" in adaptive
    generic = render_render_payload_html(
        {"template_slug": "promo-4", "items": [{"name": "x"}]}, generated_at=datetime.now(UTC)
    )
    assert "price-panel" not in generic


@pytest.mark.parametrize("currency", ["EUR", "TRY", "USD", "GBP", "CHF", "kr"])
def test_supermarket_currency_encoding_and_price_parts(currency):
    html = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-4",
            "items": [{"name": "Milk", "price": "12.99", "currency": currency}],
        },
        generated_at=datetime.now(UTC),
    )
    expected = {"EUR": "€", "TRY": "₺", "USD": "$", "GBP": "£", "CHF": "CHF", "kr": "kr"}[currency]
    assert '<meta charset="utf-8">' in html
    assert expected in html
    assert "Ã¢â€šÂ¬" not in html
    assert "�" not in html
    assert 'class="price-major"' in html and 'class="price-minor"' in html


@pytest.mark.parametrize(
    "value,currency,major,minor",
    [
        ("1.99", "EUR", "1", ",99"),
        ("12.99", "USD", "12", ".99"),
        ("999999.99", "CHF", "999999", ".99"),
        ("199", "TRY", "199", ",00"),
    ],
)
def test_supermarket_currency_formats_are_safe(value, currency, major, minor):
    html = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-4",
            "items": [{"name": "x", "price": value, "currency": currency}],
        },
        generated_at=datetime.now(UTC),
    )
    assert f'<span class="price-major">{major}</span>' in html
    assert f'<span class="price-minor">{minor}</span>' in html


@pytest.mark.parametrize(
    ("slug", "composition"),
    [
        ("supermarket-promo-4", "hero-offers"),
        ("supermarket-promo-9", "weekly-grid"),
        ("supermarket-promo-16", "catalogue-grid"),
    ],
)
def test_density_profiles_emit_distinct_retail_compositions(slug, composition):
    html = render_render_payload_html(
        {"template_slug": slug, "items": [{"name": "Offer", "price": "9.99"}]},
        generated_at=datetime.now(UTC),
    )
    assert f"composition-{composition}" in html
    assert f'"composition": "{composition}"' not in html


def test_retail_cards_use_soft_separation_and_deterministic_editorial_emphasis():
    html = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-4",
            "items": [{"name": f"Offer {index}", "price": "9.99"} for index in range(4)],
        },
        generated_at=datetime.now(UTC),
    )
    assert (
        ".composition-hero-offers .product-card{border:0;border-radius:0;background:transparent"
        in html
    )
    assert html.count('data-composition-group="hero"') == 1
    assert html.count('data-composition-group="support"') == 3
    assert 'data-emphasis="featured" data-merchandising-role="featured"' in html
    assert html.count('<article class="product-card" data-emphasis="featured"') == 1
    assert 'data-rhythm="b"' in html and 'data-rhythm="c"' in html

    weekly = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-9",
            "items": [
                {"name": "Standard first", "price": "9.99"},
                {"name": "Explicit hero", "price": "7.99", "emphasis": "featured"},
            ],
        },
        generated_at=datetime.now(UTC),
    )
    assert weekly.index("Explicit hero") < weekly.index("Standard first")
    assert (
        weekly.count(
            '<article class="product-card" data-emphasis="featured" data-merchandising-role="featured"'
        )
        == 1
    )
    assert 'data-merchandising-role="secondary"' in weekly


def test_weekly_and_compact_compositions_hide_the_safe_grid_with_grouped_whitespace():
    weekly = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-9",
            "items": [{"name": f"Offer {index}", "price": "9.99"} for index in range(9)],
        },
        generated_at=datetime.now(UTC),
    )
    assert weekly.count('data-composition-group="lead-zone"') == 3
    assert weekly.count('data-composition-group="offer-cluster-a"') == 3
    assert weekly.count('data-composition-group="offer-cluster-b"') == 3
    assert (
        ".composition-weekly-grid .product-card:nth-child(4),.composition-weekly-grid .product-card:nth-child(9){grid-column:span 5}"
        in weekly
    )
    assert (
        ".composition-weekly-grid .product-card{grid-column:span 4;border:0;border-radius:0;background:transparent"
        in weekly
    )
    assert ".composition-weekly-grid.retail-card-outlined .product-card" in weekly
    assert "border:0;background:transparent" in weekly
    weekly_treatments = re.findall(r'<article[^>]+data-price-treatment="([^"]+)"', weekly)
    assert len(weekly_treatments) == 9
    assert len(set(weekly_treatments)) >= 5
    assert len(re.findall(r'<article[^>]+data-vertical-offset="([^"]+)"', weekly)) == 9

    compact = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-16",
            "items": [{"name": f"Offer {index}", "price": "9.99"} for index in range(16)],
        },
        generated_at=datetime.now(UTC),
    )
    for cluster in ("a", "b", "c", "d"):
        assert f'data-composition-group="cluster-{cluster}"' in compact
    compact_treatments = re.findall(r'<article[^>]+data-price-treatment="([^"]+)"', compact)
    compact_tiers = re.findall(r'<article[^>]+data-image-tier="([^"]+)"', compact)
    compact_offsets = re.findall(r'<article[^>]+data-vertical-offset="([^"]+)"', compact)
    assert len(set(compact_treatments)) == 5
    assert len(set(compact_tiers)) == 4
    assert len(set(compact_offsets)) == 16
    assert ".composition-catalogue-grid .product-grid{grid-template-columns:repeat(24" in compact
    assert "background:color-mix(in srgb,var(--card-bg,#fff8e7) 96%,#fff)" in compact
    assert ".composition-catalogue-grid .product-card{grid-column:span 5" in compact
    assert "border:0;border-radius:0;background:transparent" in compact
    assert ".composition-catalogue-grid .product-card:after{content:none}" in compact


def test_image_stage_price_badge_and_header_contracts_are_semantic_and_safe():
    html = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-4",
            "template_config": {
                "header_style": "minimal",
                "price_style": "split",
                "badge_style": "burst",
                "image_treatment": "cutout",
                "show_header_title": False,
            },
            "items": [
                {
                    "name": "Large offer",
                    "image_key": "missing.png",
                    "image_has_alpha": True,
                    "price": "999999.99",
                    "currency": "CHF",
                    "badge": "25% OFF",
                }
            ],
        },
        generated_at=datetime.now(UTC),
    )
    assert "retail-header-minimal" in html
    assert "retail-price-split" in html
    assert "retail-badge-burst" in html
    assert "retail-image-cutout" in html
    assert 'data-image-stage="cutout"' in html
    assert 'class="price price-long"' in html
    assert 'data-title-visible="false"' in html
    assert '<header class="hero"' in html
    assert "<h1 " not in html


@pytest.mark.parametrize(
    "variant,selector",
    [
        ("pill", ".retail-badge-pill .promo-badge"),
        ("sticker", ".retail-badge-sticker .promo-badge"),
        ("burst", ".retail-badge-burst .promo-badge"),
        ("ribbon", ".retail-badge-ribbon .promo-badge"),
    ],
)
def test_badge_variants_emit_distinct_safe_composition(variant, selector):
    html = render_render_payload_html(
        {
            "template_slug": "supermarket-promo-9",
            "template_config": {"badge_style": variant},
            "items": [{"name": "Offer", "price": "9.99", "badge": "SAVE"}],
        },
        generated_at=datetime.now(UTC),
    )
    assert f"retail-badge-{variant}" in html
    assert selector in html
