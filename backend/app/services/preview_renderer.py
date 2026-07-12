from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Any

from app.models import Campaign, CampaignItem, Template
from app.services.catalog import resolve_effective_product


DEFAULT_TEMPLATE_SLUG = "premium-market"
DEFAULT_TEMPLATE_NAME = "Premium Market"


def render_campaign_preview_html(
    campaign: Campaign,
    template: Template | None,
    *,
    generated_at: datetime,
) -> str:
    config = dict(template.config_json) if template and isinstance(template.config_json, dict) else {}
    if campaign.market is not None and isinstance(campaign.market.promo_profile_json, dict):
        config = {**campaign.market.promo_profile_json, **config}
    slug = str(config.get("layout") or template.slug if template else DEFAULT_TEMPLATE_SLUG)
    if slug not in {"premium-market", "compact-weekly"}:
        slug = "compact-weekly" if config.get("columns") == 2 else DEFAULT_TEMPLATE_SLUG

    template_name = template.name if template else DEFAULT_TEMPLATE_NAME
    items = sorted(campaign.items, key=lambda item: (item.sort_order, item.created_at or generated_at, str(item.id)))
    styles = _style_config(slug, config)
    cards = "\n".join(_render_item_card(item, config) for item in items[:_slot_count(config)] if item.match_status != "excluded")
    if not cards:
        cards = '<div class="empty-state">Bu kampanyada henüz ürün bulunmuyor.</div>'

    generated_date = _format_date(generated_at)
    promo_title = str(config.get("promo_title") or campaign.title)
    validity_text = str(config.get("validity_text") or generated_date)
    market_name = campaign.market.name if campaign.market is not None else "LeafletPilot"
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
    html, body {{
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
    .market-logo {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      margin-bottom: 12px;
      padding: 5px 10px;
      border: 1px solid rgba(255,255,255,.55);
      border-radius: 999px;
      color: #ffffff;
      font-size: 11px;
      font-weight: 900;
      letter-spacing: .06em;
      text-transform: uppercase;
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
    .product-image {{
      display: block;
      width: 100%;
      min-height: {styles["image_min_height"]};
      max-height: 190px;
      object-fit: contain;
      border-radius: 6px;
      background: #fff;
    }}
    .product-card h2 {{
      margin: 16px 0 0;
      font-size: {styles["product_title_size"]};
      line-height: 1.18;
      min-height: {styles["product_title_min_height"]};
    }}
    .product-brand {{ margin: 10px 0 0; color: var(--accent); font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    .product-unit {{ margin: 4px 0 0; color: var(--muted); font-size: 12px; }}
    .promo-badge {{ padding: 4px 7px; border-radius: 999px; background: #fef3c7; color: #92400e; font-size: 10px; font-weight: 800; }}
    .price-row {{
      display: flex;
      flex-wrap: nowrap;
      align-items: baseline;
      gap: 6px;
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
      font-size: 13px;
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
        <div class="market-logo" aria-label="Market logo">{_text(market_name)}</div>
        <p class="eyebrow">{_text(template_name)}</p>
        <h1>{_text(promo_title)}</h1>
      </div>
      <div class="meta">
        <div>Haftalık Fırsatlar</div>
        <div>{_text(validity_text)}</div>
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
    product = item.product
    market_product = getattr(item, "_market_product", None)
    effective = resolve_effective_product(product, market_product)
    brand_name = market_product.private_brand_text if market_product and market_product.private_brand_text else (product.brand.name if product is not None and product.brand is not None else None)
    unit = item.quantity_label or item.unit_label or effective.name
    badge = market_product.badge_text if market_product and market_product.badge_text else (product.badge_text if product is not None else None)
    currency = item.currency or (market_product.currency if market_product else "EUR")
    old_price = ""
    if config.get("show_old_price", True) and item.old_price is not None:
        old_price = f'<span class="old-price">{_text(_format_money(item.old_price, currency))}</span>'

    return f"""<article class="product-card">
  {_render_product_image(item, effective)}
  <div>
    {f'<p class="product-brand">{_text(brand_name)}</p>' if brand_name else ''}
    <h2>{_text(display_name)}</h2>
    {f'<p class="product-unit">{_text(unit)}</p>' if unit else ''}
    <div class="price-row">
      {f'<span class="promo-badge">{_text(badge)}</span>' if badge else ''}
      <span class="price">{_text(_format_money(item.price, currency))}</span>
      {old_price}
    </div>
  </div>
</article>"""


def _render_product_image(item: CampaignItem, effective=None) -> str:
    if effective is None:
        effective = resolve_effective_product(item.product, getattr(item, "_market_product", None))
    if effective.image_storage_key:
        try:
            from app.services.rendering import storage_path_for_key
            path = storage_path_for_key(effective.image_storage_key)
            if path.is_file() and path.stat().st_size > 0:
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                mime_type = escape(getattr(getattr(item, "_market_product", None), "image_mime_type", None) or "image/png")
                return f'<img class="product-image" src="data:{mime_type};base64,{encoded}" alt="{_attr(item.display_name or item.incoming_name)}">'
        except (OSError, ValueError):
            pass
    images = list(item.product.images) if item.product is not None else []
    image = next((candidate for candidate in images if candidate.is_primary), None)
    image = image or (images[0] if images else None)
    if image is not None and image.storage_key:
        try:
            from app.services.rendering import storage_path_for_key

            path = storage_path_for_key(image.storage_key)
            if path.is_file() and path.stat().st_size > 0:
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                mime_type = escape(image.mime_type or "image/png")
                alt = _attr(item.display_name or item.incoming_name)
                return f'<img class="product-image" src="data:{mime_type};base64,{encoded}" alt="{alt}">'
        except (OSError, ValueError):
            pass
    return '<div class="image-placeholder">Ürün görseli</div>'


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
    dense = columns >= 4
    return {
        "accent": _safe_css_color(accent, accent_fallback),
        "accent_dark": accent_dark,
        "accent_soft": _safe_css_color(accent_soft, "#f8fafc"),
        "columns": str(columns),
        "padding": "34px" if slug == "compact-weekly" else "42px",
        "gap": "12px" if slug == "compact-weekly" else "18px",
        "card_min_height": "128px" if slug == "compact-weekly" else "235px",
        "card_padding": "10px" if dense else ("14px" if slug == "compact-weekly" else "18px"),
        "image_min_height": "76px" if dense else ("62px" if slug == "compact-weekly" else "132px"),
        "title_size": "34px" if slug == "compact-weekly" else "44px",
        "section_title_size": "18px" if slug == "compact-weekly" else "22px",
        "product_title_size": "14px" if dense else ("16px" if slug == "compact-weekly" else "18px"),
        "product_title_min_height": "34px" if dense else ("38px" if slug == "compact-weekly" else "44px"),
        "price_size": "24px" if dense or slug == "compact-weekly" else "36px",
    }


def _slot_count(config: dict[str, Any]) -> int:
    try:
        return min(max(int(config.get("slot_count") or 999), 1), 64)
    except (TypeError, ValueError):
        return 64


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
