from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.models import Campaign, CampaignItem, Template
from app.services.preview_renderer import render_campaign_preview_html


def test_preview_renderer_escapes_user_generated_text() -> None:
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
    assert "1.59 EUR" in html
    assert "Bulunamadı" in html


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
