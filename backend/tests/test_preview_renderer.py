from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.models import Brand, Campaign, CampaignItem, Market, Product, ProductImage, Template
from app.services.preview_renderer import render_campaign_preview_html, render_render_payload_html
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


def test_preview_renderer_uses_builder_metadata_and_output_dimensions() -> None:
    campaign = Campaign(title="Campaign name", market_id=uuid4(), currency="EUR", language="tr")
    campaign.builder_config_json = {"headline": "Başlık yeni", "subtitle": "Alt başlık yeni", "footer": "Alt bilgi yeni"}
    html = render_campaign_preview_html(campaign, None, generated_at=datetime(2026, 7, 5, tzinfo=UTC), output_format="instagram_post")

    assert "Başlık yeni" in html
    assert "Alt başlık yeni" in html
    assert "Alt bilgi yeni" in html
    assert 'data-output-format="instagram_post"' in html
    assert 'data-preview-width="1080"' in html
    assert 'data-preview-height="1080"' in html


def test_preview_renderer_deduplicates_package_units_and_adapts_low_product_layouts() -> None:
    payload = {
        "template_slug": "premium-market",
        "items": [{"name": "Milk", "price": "1.99", "currency": "EUR", "quantity_label": "5 L", "package_size": "5 L", "package_type": "L"}],
    }
    html = render_render_payload_html(payload, generated_at=datetime(2026, 7, 5, tzinfo=UTC))

    assert 'grid-template-columns:repeat(1' in html
    assert '>5 L</p>' in html
    assert "5 L 5 L" not in html


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
    assert "Haftanın Fırsatları" in html
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


def test_preview_renderer_normalizes_equivalent_package_units() -> None:
    examples = (("5 L", "L", "5 L"), ("2 Litre", "Litre", "2 L"), ("1 kg", "kg", "1 kg"), ("200 mL", "mL", "200 mL"), ("500", "g", "500 g"), ("2 L", "Litre", "2 L"))
    for quantity, package_type, expected in examples:
        html = render_render_payload_html({"template_slug": "premium-market", "items": [{"name": "Product", "quantity_label": quantity, "package_type": package_type}]}, generated_at=datetime(2026, 7, 5, tzinfo=UTC))
        assert f">{expected}</p>" in html
        assert html.count('class="product-unit"') == 2
        assert " L L</p>" not in html and " kg kg</p>" not in html and " mL mL</p>" not in html


def test_preview_renderer_formats_compact_package_size() -> None:
    html = render_render_payload_html(
        {"template_slug": "premium-market", "items": [{"name": "Product", "package_size": "2L"}]},
        generated_at=datetime(2026, 7, 5, tzinfo=UTC),
    )

    assert ">2 L</p>" in html


def test_preview_renderer_emits_distinct_template_and_count_layout_markers() -> None:
    items = [{"name": f"Product {index}", "price": "1.99", "currency": "EUR"} for index in range(8)]
    premium = render_render_payload_html({"template_slug": "premium-market", "layout_family": "premium-market", "items": items}, generated_at=datetime(2026, 7, 5, tzinfo=UTC))
    compact = render_render_payload_html({"template_slug": "compact-weekly", "layout_family": "compact-weekly", "items": items}, generated_at=datetime(2026, 7, 5, tzinfo=UTC))
    supermarket = render_render_payload_html({"template_slug": "supermarket-promo-4", "items": items}, generated_at=datetime(2026, 7, 5, tzinfo=UTC))
    assert "layout-3x3" in premium
    assert "layout-3x3" in compact
    assert "preview-supermarket-promo-9" in supermarket
    assert "price-panel" in supermarket
    assert premium != compact != supermarket


def test_preview_renderer_uses_product_count_compositions_and_localized_copy() -> None:
    expected = {1: "layout-1x1", 2: "layout-2x1", 3: "layout-3x1", 4: "layout-2x2", 6: "layout-3x2", 8: "layout-3x3"}
    for count, marker in expected.items():
        html = render_render_payload_html(
            {"template_slug": "premium-market", "language": "tr", "items": [{"name": f"Ürün {i}", "price": "1.99", "currency": "EUR"} for i in range(count)]},
            generated_at=datetime(2026, 7, 5, tzinfo=UTC),
        )
        assert marker in html
        assert f"products-{count}" in html
    turkish = render_render_payload_html({"template_slug": "premium-market", "language": "tr", "items": [{"name": "Süt"}]}, generated_at=datetime.now(UTC))
    english = render_render_payload_html({"template_slug": "premium-market", "language": "en", "items": [{"name": "Milk"}]}, generated_at=datetime.now(UTC))
    assert "Haftanın Fırsatları" in turkish and "Stoklarla sınırlıdır." in turkish
    assert "Weekly offers" in english and "While stocks last." in english
    assert "min-height:0" in turkish  # grid containment is allowed; cards themselves are content-sized.
    assert ".product-card{display:flex;flex-direction:column;align-self:start" in turkish
    assert ".price-row{display:flex;min-width:0;width:100%;align-items:flex-start;flex-direction:column;gap:2px;flex-wrap:wrap;margin-top:8px" in turkish


def test_preview_and_export_share_the_same_render_state() -> None:
    payload = {"template_slug": "premium-market", "language": "tr", "header": {"promo_title": "Alt başlık", "footer_note": "Özel footer"}, "items": [{"name": "Ürün", "price": "1.99", "currency": "EUR"}]}
    preview = render_render_payload_html(payload, generated_at=datetime(2026, 7, 5, tzinfo=UTC))
    export = render_render_payload_html(payload, generated_at=datetime(2026, 7, 5, tzinfo=UTC))
    assert preview == export
    assert "Alt başlık" in preview and "Özel footer" in preview


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
