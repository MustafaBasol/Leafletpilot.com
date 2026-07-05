from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Any

from app.models import Campaign, CampaignItem, Template


DEFAULT_TEMPLATE_SLUG = "premium-market"
DEFAULT_TEMPLATE_NAME = "Premium Market"


def render_campaign_preview_html(
    campaign: Campaign,
    template: Template | None,
    *,
    generated_at: datetime,
) -> str:
    config = template.config_json if template and isinstance(template.config_json, dict) else {}
    slug = str(config.get("layout") or template.slug if template else DEFAULT_TEMPLATE_SLUG)
    if slug not in {"premium-market", "compact-weekly"}:
        slug = "compact-weekly" if config.get("columns") == 2 else DEFAULT_TEMPLATE_SLUG

    template_name = template.name if template else DEFAULT_TEMPLATE_NAME
    items = sorted(campaign.items, key=lambda item: (item.sort_order, item.created_at or generated_at, str(item.id)))
    styles = _style_config(slug, config)
    cards = "\n".join(_render_item_card(item, config) for item in items)
    if not cards:
        cards = '<div class="empty-state">Bu kampanyada henüz ürün bulunmuyor.</div>'

    return f"""<!doctype html>
<html lang="{_attr(campaign.language or "tr")}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_text(campaign.title)} - {_text(template_name)}</title>
  <style>
    :root {{
      color-scheme: light;
      --accent: {styles["accent"]};
      --accent-soft: {styles["accent_soft"]};
      --ink: #1f2933;
      --muted: #64748b;
      --paper: #fffdf8;
      --line: #e2e8f0;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #eef2f6;
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
    }}
    .preview-document {{
      width: min(100%, 960px);
      min-height: 720px;
      margin: 0 auto;
      padding: {styles["padding"]};
      background: var(--paper);
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      padding-bottom: 18px;
      border-bottom: 4px solid var(--accent);
    }}
    .eyebrow {{
      margin: 0 0 8px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0;
      font-size: {styles["title_size"]};
      line-height: 1.05;
    }}
    .meta {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.7;
      text-align: right;
      white-space: nowrap;
    }}
    .product-grid {{
      display: grid;
      grid-template-columns: repeat({styles["columns"]}, minmax(0, 1fr));
      gap: {styles["gap"]};
      margin-top: 24px;
    }}
    .product-card {{
      display: grid;
      grid-template-columns: {styles["image_width"]} minmax(0, 1fr);
      gap: 14px;
      min-height: 132px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }}
    .image-placeholder {{
      display: grid;
      min-height: 96px;
      place-items: center;
      border-radius: 6px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
    }}
    .product-card h2 {{
      margin: 0 0 8px;
      font-size: {styles["product_title_size"]};
      line-height: 1.2;
    }}
    .price-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 8px;
      margin-top: 10px;
    }}
    .price {{
      color: var(--accent);
      font-size: {styles["price_size"]};
      font-weight: 800;
    }}
    .old-price {{
      color: var(--muted);
      font-size: 15px;
      text-decoration: line-through;
    }}
    .badge {{
      display: inline-block;
      margin-top: 8px;
      padding: 4px 8px;
      border-radius: 999px;
      background: #edf2f7;
      color: #334155;
      font-size: 11px;
      font-weight: 700;
    }}
    .badge.matched, .badge.manual-selected {{ background: #dcfce7; color: #166534; }}
    .badge.low-confidence {{ background: #fef3c7; color: #92400e; }}
    .badge.not-found, .badge.new-product-needed {{ background: #fee2e2; color: #991b1b; }}
    .empty-state {{
      grid-column: 1 / -1;
      padding: 36px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      text-align: center;
      background: #ffffff;
    }}
  </style>
</head>
<body>
  <main class="preview-document preview-{_attr(slug)}">
    <header class="hero">
      <div>
        <p class="eyebrow">{_text(template_name)}</p>
        <h1>{_text(campaign.title)}</h1>
      </div>
      <div class="meta">
        <div>Üretilme: {_text(generated_at.isoformat())}</div>
        <div>Para birimi: {_text(campaign.currency)}</div>
      </div>
    </header>
    <section class="product-grid" aria-label="Kampanya ürünleri">
      {cards}
    </section>
  </main>
</body>
</html>"""


def _render_item_card(item: CampaignItem, config: dict[str, Any]) -> str:
    display_name = item.display_name or item.incoming_name
    currency = item.currency or "EUR"
    old_price = ""
    if config.get("show_old_price", True) and item.old_price is not None:
        old_price = f'<span class="old-price">{_text(_format_money(item.old_price, currency))}</span>'
    badge = ""
    if config.get("show_badges", True):
        badge = f'<span class="badge {_attr(_status_class(item.match_status))}">{_text(_status_label(item.match_status))}</span>'

    return f"""<article class="product-card">
  <div class="image-placeholder">Görsel</div>
  <div>
    <h2>{_text(display_name)}</h2>
    <div class="price-row">
      <span class="price">{_text(_format_money(item.price, currency))}</span>
      {old_price}
    </div>
    {badge}
  </div>
</article>"""


def _style_config(slug: str, config: dict[str, Any]) -> dict[str, str]:
    try:
        columns = int(config.get("columns") or (2 if slug == "compact-weekly" else 3))
    except (TypeError, ValueError):
        columns = 2 if slug == "compact-weekly" else 3
    columns = min(max(columns, 1), 4)
    accent = str(config.get("accent_color") or ("#0f766e" if slug == "compact-weekly" else "#b91c1c"))
    accent_soft = str(config.get("accent_soft_color") or ("#ccfbf1" if slug == "compact-weekly" else "#fee2e2"))
    return {
        "accent": _safe_css_color(accent, "#b91c1c"),
        "accent_soft": _safe_css_color(accent_soft, "#fee2e2"),
        "columns": str(columns),
        "padding": "28px" if slug == "compact-weekly" else "36px",
        "gap": "12px" if slug == "compact-weekly" else "18px",
        "image_width": "70px" if slug == "compact-weekly" else "88px",
        "title_size": "34px" if slug == "compact-weekly" else "44px",
        "product_title_size": "16px" if slug == "compact-weekly" else "18px",
        "price_size": "24px" if slug == "compact-weekly" else "30px",
    }


def _format_money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return f"- {currency}"
    return f"{value:.2f} {currency}"


def _status_label(status: str) -> str:
    labels = {
        "matched": "Eşleşti",
        "manual_selected": "Manuel seçildi",
        "low_confidence": "Kontrol gerekli",
        "not_found": "Bulunamadı",
        "new_product_needed": "Yeni ürün gerekli",
        "use_without_image": "Görselsiz devam",
        "excluded": "Kampanyadan çıkarıldı",
    }
    return labels.get(status, status)


def _status_class(status: str) -> str:
    return status.replace("_", "-")


def _text(value: object) -> str:
    return escape(str(value), quote=False)


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def _safe_css_color(value: str, fallback: str) -> str:
    value = value.strip()
    if len(value) in {4, 7} and value.startswith("#") and all(char in "0123456789abcdefABCDEF" for char in value[1:]):
        return value
    return fallback
