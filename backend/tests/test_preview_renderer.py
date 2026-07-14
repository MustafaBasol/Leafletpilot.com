from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.models import Brand, Campaign, CampaignItem, Market, Product, ProductImage, Template
from app.services.preview_renderer import render_campaign_preview_html
from app.services.campaign_rendering import render_campaign_snapshot_html


def test_preview_renderer_escapes_user_generated_text_and_hides_diagnostics() -> None:
    market_id = uuid4()
    campaign = Campaign(
        title="<script>alert('campaign')</script>",
        market_id=market_id,
        currency="EUR",
        language="tr",
    )
    campaign.items = [
        CampaignItem(
            raw_line="<b>raw</b>",
            incoming_name="<img src=x onerror=alert(1)>",
            display_name="Bal & Peynir <özel>",
            price=Decimal("1.59"),
            old_price=Decimal("1.99"),
            currency="EUR",
            market_id=market_id,
            match_status="not_found",
        )
    ]
    template = Template(
        name="Premium <Market>",
        slug="premium-market",
        template_type="premium",
        is_global=True,
        is_active=True,
        config_json={"layout": "premium-market", "show_badges": True},
    )

    html = render_campaign_preview_html(
        campaign,
        template,
        generated_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )

    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;alert('campaign')&lt;/script&gt;" in html
    assert "Bal &amp; Peynir &lt;özel&gt;" in html
    assert "1,59€" in html
    assert "1,99€" in html
    assert 'class="old-price"' in html
    assert "1.59 EUR" not in html
    assert "Bulunamadı" not in html
    assert "not-found" not in html
    assert "2026-07-05T10:00:00+00:00" not in html
    assert "05.07.2026" in html


def test_preview_renderer_handles_empty_campaign_items() -> None:
    campaign = Campaign(
        title="Boş Kampanya",
        market_id=uuid4(),
        currency="EUR",
        language="tr",
    )

    html = render_campaign_preview_html(
        campaign,
        None,
        generated_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )

    assert "Premium Market" in html
    assert "Bu kampanyada henüz ürün bulunmuyor." in html
    assert "Boş Kampanya" in html


def test_preview_renderer_renders_premium_market_without_errors() -> None:
    campaign = _campaign_with_items("Premium Kampanya", "matched")
    template = Template(
        name="Premium Market",
        slug="premium-market",
        template_type="premium",
        is_global=True,
        is_active=True,
        config_json={"layout": "premium-market", "columns": 3, "show_old_price": True},
    )

    html = render_campaign_preview_html(
        campaign,
        template,
        generated_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )

    assert "preview-premium-market" in html
    assert "Haftalık Fırsatlar" in html
    assert "Ürün görseli" in html
    assert "2 ürün" in html


def test_preview_renderer_renders_compact_weekly_without_errors() -> None:
    campaign = _campaign_with_items("Compact Kampanya", "low_confidence")
    template = Template(
        name="Compact Weekly",
        slug="compact-weekly",
        template_type="compact",
        is_global=True,
        is_active=True,
        config_json={"layout": "compact-weekly", "columns": 2, "show_old_price": True},
    )

    html = render_campaign_preview_html(
        campaign,
        template,
        generated_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )

    assert "preview-compact-weekly" in html
    assert "Compact Weekly" in html
    assert "Kontrol gerekli" not in html
    assert "0,89€" in html


def test_preview_renderer_renders_hydrated_market_product_graph_without_io() -> None:
    market = Market(
        name="Hydrated Market",
        slug="hydrated-market",
        promo_profile_json={"promo_title": "Market Deals"},
    )
    brand = Brand(name="Fresh Brand", slug="fresh-brand")
    product = Product(
        name="Fresh Product",
        package_size="500g",
        badge_text="New",
        brand=brand,
        images=[ProductImage(storage_key="not-present.png", is_primary=True)],
    )
    campaign = Campaign(
        title="Hydrated Campaign",
        market=market,
        items=[
            CampaignItem(
                incoming_name="Fresh Product",
                display_name="Fresh Product",
                price=Decimal("2.49"),
                quantity_label="2 x 500g",
                currency="EUR",
                match_status="matched",
                product=product,
            )
        ],
    )
    template = Template(
        name="Premium Market",
        slug="premium-market",
        template_type="premium",
        config_json={"layout": "premium-market"},
    )

    html = render_campaign_preview_html(
        campaign,
        template,
        generated_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )

    assert "Market Deals" in html
    assert 'class="product-brand">Fresh Brand' in html
    assert 'class="product-unit">2 x 500g' in html
    assert 'class="promo-badge">New' in html
    assert "Fresh Product" in html
    assert "not-present.png" not in html


def test_frozen_snapshot_renderer_uses_snapshot_values_after_source_mutation() -> None:
    snapshot = {
        "title": "Frozen Campaign",
        "language": "tr",
        "currency": "EUR",
        "market_name": "Frozen Market",
        "template_name": "Historical v1",
        "template_slug": "premium-market",
        "template_config": {"layout": "premium-market", "accent_color": "#2563eb"},
        "items": [{"id": str(uuid4()), "name": "Original Product", "resolved_name": "Original Product", "price": "8.99", "old_price": "10.99", "currency": "EUR", "sort_order": 0}],
    }

    html = render_campaign_snapshot_html(snapshot, generated_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC))

    assert "Original Product" in html
    assert "8,99" in html
    assert "#2563eb" in html
    assert "MUTATED" not in html


def _campaign_with_items(title: str, match_status: str) -> Campaign:
    market_id = uuid4()
    campaign = Campaign(
        title=title,
        market_id=market_id,
        currency="EUR",
        language="tr",
    )
    campaign.items = [
        CampaignItem(
            raw_line="Pınar Süt 1L - 0.89€",
            incoming_name="Pınar Süt 1L",
            display_name="Pınar Süt 1L",
            price=Decimal("0.89"),
            old_price=Decimal("1.09"),
            currency="EUR",
            market_id=market_id,
            match_status=match_status,
            sort_order=1,
        ),
        CampaignItem(
            raw_line="Nutella 750g - 4.99€",
            incoming_name="Nutella 750g",
            display_name="Nutella 750g",
            price=Decimal("4.99"),
            old_price=None,
            currency="EUR",
            market_id=market_id,
            match_status=match_status,
            sort_order=2,
        ),
    ]
    return campaign
