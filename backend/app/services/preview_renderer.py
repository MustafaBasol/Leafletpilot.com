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

    generated_date = _format_date(generated_at)
    footer_note = str(config.get("footer_note") or "Stoklarla sınırlıdır. Görseller temsilidir.")

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
      --accent-dark: {styles["accent_dark"]};
      --accent-soft: {styles["accent_soft"]};
      --ink: #16202a;
      --muted: #64748b;
      --paper: #fffaf0;
      --surface: #ffffff;
      --line: #e5e7eb;
      --soft-line: #f1f5f9;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
    }}
    .preview-document {{
      width: min(100%, 960px);
      min-height: 100vh;
      margin: 0 auto;
      padding: {styles["padding"]};
      background: var(--paper);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 28px;
      padding: 24px 26px;
      border-radius: 8px;
      background: linear-gradient(135deg, var(--accent), var(--accent-dark));
      color: #ffffff;
    }}
    .eyebrow {{
      margin: 0 0 8px;
      color: #ffe8b7;
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
      color: #fff7ed;
      font-size: 13px;
      font-weight: 700;
      line-height: 1.5;
      text-align: right;
      white-space: nowrap;
    }}
    .section-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      margin: 28px 0 0;
      color: var(--accent-dark);
      font-size: {styles["section_title_size"]};
      font-weight: 800;
    }}
    .section-title span {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }}
    .product-grid {{
      display: grid;
      grid-template-columns: repeat({styles["columns"]}, minmax(0, 1fr));
      grid-auto-rows: minmax({styles["card_min_height"]}, 1fr);
      gap: {styles["gap"]};
      flex: 1;
      align-content: stretch;
      margin-top: 18px;
    }}
    .product-card {{
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: {styles["card_min_height"]};
      padding: {styles["card_padding"]};
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
    }}
    .image-placeholder {{
      display: flex;
      min-height: {styles["image_min_height"]};
      align-items: center;
      justify-content: center;
      border-radius: 6px;
      background: linear-gradient(145deg, #f8fafc, var(--accent-soft));
      border: 1px solid var(--soft-line);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-align: center;
    }}
    .product-card h2 {{
      margin: 16px 0 0;
      font-size: {styles["product_title_size"]};
      line-height: 1.18;
      min-height: {styles["product_title_min_height"]};
    }}
    .price-row {{
      display: flex;
      flex-wrap: nowrap;
      align-items: baseline;
      gap: 10px;
      margin-top: auto;
      padding-top: 14px;
    }}
    .price {{
      color: var(--accent);
      font-size: {styles["price_size"]};
      font-weight: 900;
      letter-spacing: 0;
      white-space: nowrap;
    }}
    .old-price {{
      color: var(--muted);
      font-size: 15px;
      text-decoration: line-through;
      white-space: nowrap;
    }}
    .empty-state {{
      grid-column: 1 / -1;
      align-self: center;
      padding: 56px 36px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      text-align: center;
      background: var(--surface);
    }}
    .footer {{
      display: flex;
      justify-content: space-between;
      gap: 20px;
      margin-top: 24px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
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
        <div>Haftalık Fırsatlar</div>
        <div>{_text(generated_date)}</div>
      </div>
    </header>
    <div class="section-title">
      <strong>Haftalık Fırsatlar</strong>
      <span>{len(items)} ürün</span>
    </div>
    <section class="product-grid" aria-label="Kampanya ürünleri">
      {cards}
    </section>
    <footer class="footer">
      <span>{_text(footer_note)}</span>
      <span>{_text(template_name)}</span>
    </footer>
  </main>
</body>
</html>"""


def _render_item_card(item: CampaignItem, config: dict[str, Any]) -> str:
    display_name = item.display_name or item.incoming_name
    currency = item.currency or "EUR"
    old_price = ""
    if config.get("show_old_price", True) and item.old_price is not None:
        old_price = f'<span class="old-price">{_text(_format_money(item.old_price, currency))}</span>'

    return f"""<article class="product-card">
  <div class="image-placeholder">Ürün görseli</div>
  <div>
    <h2>{_text(display_name)}</h2>
    <div class="price-row">
      <span class="price">{_text(_format_money(item.price, currency))}</span>
      {old_price}
    </div>
  </div>
</article>"""


def _style_config(slug: str, config: dict[str, Any]) -> dict[str, str]:
    try:
        columns = int(config.get("columns") or (2 if slug == "compact-weekly" else 3))
    except (TypeError, ValueError):
        columns = 2 if slug == "compact-weekly" else 3
    columns = min(max(columns, 1), 4)
    accent = str(config.get("accent_color") or ("#0f766e" if slug == "compact-weekly" else "#c1121f"))
    accent_soft = str(config.get("accent_soft_color") or ("#ccfbf1" if slug == "compact-weekly" else "#fff1f2"))
    accent_fallback = "#0f766e" if slug == "compact-weekly" else "#c1121f"
    accent_dark = "#115e59" if slug == "compact-weekly" else "#003049"
    return {
        "accent": _safe_css_color(accent, accent_fallback),
        "accent_dark": accent_dark,
        "accent_soft": _safe_css_color(accent_soft, "#f8fafc"),
        "columns": str(columns),
        "padding": "34px" if slug == "compact-weekly" else "42px",
        "gap": "12px" if slug == "compact-weekly" else "18px",
        "card_min_height": "128px" if slug == "compact-weekly" else "235px",
        "card_padding": "14px" if slug == "compact-weekly" else "18px",
        "image_min_height": "62px" if slug == "compact-weekly" else "132px",
        "title_size": "34px" if slug == "compact-weekly" else "44px",
        "section_title_size": "18px" if slug == "compact-weekly" else "22px",
        "product_title_size": "16px" if slug == "compact-weekly" else "18px",
        "product_title_min_height": "38px" if slug == "compact-weekly" else "44px",
        "price_size": "24px" if slug == "compact-weekly" else "36px",
    }


def _format_money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "-"
    amount = f"{value:.2f}".replace(".", ",")
    symbol = _currency_symbol(currency)
    return f"{amount}{symbol}"


def _currency_symbol(currency: str) -> str:
    symbols = {
        "EUR": "€",
        "TRY": "₺",
        "USD": "$",
        "GBP": "£",
    }
    return symbols.get(str(currency).upper(), f" {currency}")


def _format_date(value: datetime) -> str:
    return value.strftime("%d.%m.%Y")


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
