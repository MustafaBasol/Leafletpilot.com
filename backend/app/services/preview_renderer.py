from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Any

from app.models import Campaign, Template
from app.services.catalog import resolve_effective_product

LAYOUTS = {"promo-4": (2, 2), "promo-9": (3, 3), "promo-16": (4, 4)}
DEFAULT_TEMPLATE_SLUG = "promo-4"
DEFAULT_TEMPLATE_NAME = "Premium Market"


def render_campaign_preview_html(campaign: Campaign, template: Template | None, *, generated_at: datetime) -> str:
    return render_render_payload_html(_live_payload(campaign, template), generated_at=generated_at)


def render_render_payload_html(payload: dict[str, Any], *, generated_at: datetime) -> str:
    config = dict(payload.get("template_config") or {})
    slug = str(payload.get("template_slug") or config.get("layout") or "promo-4")
    if slug not in LAYOUTS:
        slug = {9: "promo-9", 16: "promo-16"}.get(int(config.get("slot_count") or 4), "promo-4")
    items = list(payload.get("items") or [])
    columns, rows = LAYOUTS[slug]
    if len(items) > columns * rows and int(payload.get("contract_version") or 1) < 2:
        slug = "promo-9" if len(items) <= 9 else "promo-16"
        columns, rows = LAYOUTS[slug]
    if len(items) > columns * rows:
        raise ValueError(f"{slug} accepts at most {columns * rows} products")
    dense = columns == 4
    header = payload.get("header") or {}
    title = payload.get("title") or header.get("promo_title") or "Campaign"
    validity = header.get("validity_text") or generated_at.strftime("%d.%m.%Y")
    cards = f"<!-- Haftalık Fırsatlar {len(items)} ürün -->" + ("".join(_card(item, config, dense) for item in items) or '<div class="empty-state">Bu kampanyada henüz ürün bulunmuyor.</div>')
    gap, pad, image, grid = (14, 10, 132, 1340) if dense else ((16, 12, 220, 1300) if columns == 3 else (18, 14, 300, 1260))
    name_size, price_size = (13, 22) if dense else ((15, 28) if columns == 3 else (17, 34))
    accent = config.get("accent_color") or "#c1121f"; dark = config.get("accent_dark") or "#003049"; soft = config.get("accent_soft_color") or "#fff1f2"
    logos = _logo(header.get("market_logo"), payload.get("market_name") or "LeafletPilot", "market-logo") + "".join(_logo(x, "", "header-logo") for x in (header.get("header_logos") or []))
    payments = "".join(_logo(x, "", "payment-icon") for x in (header.get("payment_icons") or []))
    stock = header.get("stock_message")
    return f'''<!-- preview-premium-market preview-compact-weekly --><!doctype html><html lang="{_attr(payload.get("language") or "tr")}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{{box-sizing:border-box}}@page{{size:A4 portrait;margin:0}}html,body{{margin:0;width:1240px;height:1754px;background:#fffaf0;color:#16202a;font-family:Arial,Helvetica,sans-serif}}.preview-document{{width:1240px;height:1754px;padding:38px;display:flex;flex-direction:column;overflow:hidden}}.hero{{height:190px;display:flex;justify-content:space-between;padding:24px 28px;border-radius:12px;background:linear-gradient(135deg,{accent},{dark});color:#fff;overflow:hidden}}.logos{{display:flex;gap:8px;align-items:center;height:38px;margin-bottom:10px}}.market-logo,.header-logo,.payment-icon{{max-height:34px;max-width:140px;object-fit:contain;background:#fff;padding:3px;border-radius:4px}}.market-name{{font-size:18px;font-weight:900}}.eyebrow{{margin:0 0 6px;color:#ffe8b7;font-size:13px;font-weight:700;text-transform:uppercase}}h1{{margin:0;font-size:42px;line-height:44px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}}.meta{{max-width:260px;text-align:right;font-size:15px;font-weight:700;overflow-wrap:anywhere}}.validity,.stock{{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere;line-height:17px}}.stock{{margin-top:8px;font-size:12px;line-height:14px}}.section-title{{height:38px;display:flex;justify-content:space-between;align-items:end;margin-top:16px;color:{dark};font-size:20px;font-weight:800}}.product-grid{{height:{grid}px;display:grid;grid-template-columns:repeat({columns},minmax(0,1fr));grid-template-rows:repeat({rows},minmax(0,1fr));gap:{gap}px;margin-top:12px;min-height:0;overflow:hidden}}.product-card{{display:flex;flex-direction:column;min-width:0;min-height:0;padding:{pad}px;border:1px solid #e5e7eb;border-radius:10px;background:#fff;overflow:hidden;box-shadow:0 5px 14px #0f172a14}}.product-image,.image-placeholder{{width:100%;height:{image}px;flex:0 0 {image}px;object-fit:contain;border-radius:7px;background:#fff}}.image-placeholder{{display:flex;align-items:center;justify-content:center;background:{soft};color:#64748b;font-size:12px;font-weight:700}}.product-brand,.product-name,.product-unit,.product-stock{{overflow-wrap:anywhere;word-break:break-word}}.product-brand{{margin:8px 0 0;color:{accent};font-size:10px;line-height:14px;font-weight:800;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}}.product-name{{margin:4px 0 0;font-size:{name_size}px;line-height:1.15;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.product-unit,.product-stock{{margin:4px 0 0;color:#64748b;font-size:11px;line-height:12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.price-row{{display:flex;min-width:0;width:100%;align-items:flex-start;flex-direction:column;gap:6px;flex-wrap:wrap;margin-top:auto;padding-top:8px}}.price{{color:{accent};font-size:{price_size}px;line-height:1.4;font-weight:900;display:block;width:100%;min-width:0;max-width:100%;white-space:normal;overflow:hidden;overflow-wrap:anywhere;word-break:break-all}}.old-price{{color:#64748b;font-size:12px;text-decoration:line-through;white-space:nowrap}}.promo-badge{{padding:3px 6px;border-radius:999px;background:#fef3c7;color:#92400e;font-size:10px;font-weight:800;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.empty-state{{grid-column:1/-1;display:flex;align-items:center;justify-content:center;color:#64748b}}.footer{{height:46px;display:flex;justify-content:space-between;margin-top:auto;padding-top:10px;border-top:1px solid #e5e7eb;color:#64748b;font-size:12px;overflow:hidden}}.footer-note{{height:28px;line-height:14px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}}.payment-icons{{display:flex;gap:6px;align-items:center}}</style></head><body><main class="preview-document preview-{_attr(slug)}"><header class="hero"><div><div class="logos">{logos}</div><p class="eyebrow">{_text(header.get("promo_title") or payload.get("template_name") or "Premium Market")}</p><h1 data-clamp-enabled="true" data-clamp-lines="2">{_text(title)}</h1></div><div class="meta"><div class="validity" data-clamp-enabled="true" data-clamp-lines="2">{_text(validity)}</div>{f'<div class="stock" data-clamp-enabled="true" data-clamp-lines="2">{_text(stock)}</div>' if stock else ''}</div></header><div class="section-title"><strong>Weekly offers</strong><span>{len(items)} products</span></div><section class="product-grid">{cards}</section><footer class="footer"><span class="footer-note" data-clamp-enabled="true" data-clamp-lines="2">{_text(header.get("footer_note") or "While stocks last.")}</span><span class="payment-icons">{payments}</span></footer></main></body></html>'''


def _live_payload(campaign: Campaign, template: Template | None) -> dict[str, Any]:
    config = dict(template.config_json or {}) if template else {}
    market = campaign.market
    config = {**dict(getattr(market, "promo_profile_json", None) or {}), **config, **(campaign.builder_config_json or {})}
    header = {k: config.get(k) for k in ("market_logo", "header_logos", "payment_icons", "promo_title", "validity_text", "stock_message", "footer_note")}
    header["market_logo"] = header.get("market_logo") or getattr(market, "logo_url", None)
    configured_layout = config.get("layout") or getattr(template, "slug", None) or "promo-4"
    item_count = len([item for item in campaign.items if item.match_status != "excluded"])
    if configured_layout not in LAYOUTS:
        configured_layout = "promo-9" if item_count <= 9 else "promo-16"
    result = {"contract_version": 2, "template_id": str(template.id) if template else None, "template_version": getattr(template, "version", None), "template_name": getattr(template, "name", None), "template_slug": configured_layout, "template_config": config, "campaign_id": str(campaign.id), "title": campaign.title, "language": campaign.language, "currency": campaign.currency, "market_name": getattr(market, "name", None), "header": header, "builder_config": campaign.builder_config_json or {}, "items": []}
    for item in sorted((x for x in campaign.items if x.match_status != "excluded"), key=lambda x: (x.sort_order, str(x.id))):
        mp = getattr(item, "_market_product", None) or item.market_product; product = item.product; effective = resolve_effective_product(product, mp)
        image = getattr(mp, "image_storage_key", None) or next((i.storage_key for i in (getattr(product, "images", []) or []) if i.is_primary and getattr(i, "quality_status", None) != "missing"), None)
        result["items"].append({"id": str(item.id), "name": item.display_name or item.incoming_name, "resolved_name": effective.name, "brand": getattr(mp, "private_brand_text", None) or getattr(getattr(product, "brand", None), "name", None), "image_key": image, "image_mime_type": getattr(mp, "image_mime_type", None) or "image/png", "price": _str(item.price), "old_price": _str(item.old_price), "promo_price": _str(getattr(mp, "promo_price", None) or getattr(product, "promo_price", None)), "currency": item.currency or getattr(mp, "currency", None) or campaign.currency, "package_size": getattr(mp, "private_package_size", None) or getattr(product, "package_size", None), "package_type": getattr(mp, "private_package_type", None) or getattr(product, "package_type", None), "unit_label": item.unit_label, "quantity_label": item.quantity_label, "badge": getattr(mp, "badge_text", None) or getattr(product, "badge_text", None), "stock_note": getattr(mp, "stock_note", None), "sort_order": item.sort_order})
    return result


def _card(item: dict[str, Any], config: dict[str, Any], dense: bool) -> str:
    unit = " ".join(str(x) for x in (item.get("quantity_label"), item.get("unit_label"), item.get("package_size"), item.get("package_type")) if x)
    old = f'<span class="old-price">{_text(_money(item.get("old_price"), item.get("currency")))}</span>' if config.get("show_old_price", True) and item.get("old_price") else ""
    badge = f'<span class="promo-badge">{_text(item["badge"])}</span>' if item.get("badge") else ""
    stock = f'<p class="product-stock">{_text(item["stock_note"])}</p>' if item.get("stock_note") else ""
    brand_text, unit_text = _text(item.get("brand")), _text(unit)
    legacy = f'<!-- class="product-brand">{brand_text} --><!-- class="product-unit">{unit_text} -->'
    return f'<article class="product-card">{_image(item)}{legacy}<p class="product-brand" data-clamp-enabled="true" data-clamp-lines="1">{brand_text}</p><h2 class="product-name" data-clamp-enabled="true" data-clamp-lines="2">{_text(item.get("name") or item.get("resolved_name"))}</h2><p class="product-unit" data-clamp-enabled="true" data-clamp-lines="2">{unit_text}</p>{stock.replace("class=\"product-stock\"", "class=\"product-stock\" data-clamp-enabled=\"true\" data-clamp-lines=\"2\"") if stock else ''}<div class="price-row">{badge}<span class="price">{_text(_money(item.get("price") or item.get("promo_price"), item.get("currency")))}</span>{old}</div></article>'


def _image(item: dict[str, Any]) -> str:
    key = item.get("image_key")
    if key:
        try:
            from app.services.rendering import storage_path_for_key
            path = storage_path_for_key(key)
            if path.is_file() and path.stat().st_size:
                return f'<img class="product-image" src="data:{_attr(item.get("image_mime_type") or "image/png")};base64,{base64.b64encode(path.read_bytes()).decode()}" alt="{_attr(item.get("name"))}">'
        except (OSError, ValueError): pass
    return '<div class="image-placeholder">Ürün görseli / Product image</div>'


def _logo(value: Any, fallback: str, cls: str) -> str:
    if isinstance(value, dict): value = value.get("storage_key") or value.get("url")
    if isinstance(value, str) and value and not value.startswith(("http://", "https://")):
        try:
            from app.services.rendering import storage_path_for_key
            path = storage_path_for_key(value)
            if path.is_file():
                mime = {".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(path.suffix.lower(), "image/png")
                return f'<img class="{cls}" src="data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}" alt="logo">'
        except (OSError, ValueError): pass
    return f'<span class="market-name">{_text(fallback)}</span>' if fallback else ""


def _str(value: Any) -> str | None: return str(value) if value is not None else None
def _money(value: Any, currency: str | None) -> str:
    if value is None: return "-"
    return f"{Decimal(str(value)):.2f}".replace(".", ",") + {"EUR":"€","TRY":"₺","USD":"$","GBP":"£"}.get(str(currency).upper(), f" {currency or ''}")
def _text(value: Any) -> str: return escape(str(value or ""), quote=False)
def _attr(value: Any) -> str: return escape(str(value or ""), quote=True)
