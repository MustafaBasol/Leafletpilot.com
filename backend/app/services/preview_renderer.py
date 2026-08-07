from __future__ import annotations

import base64
import re
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Any

from app.models import Campaign, Template
from app.services.catalog import resolve_effective_product
from app.services.image_pipeline import stored_flyer_image_has_alpha
from app.services.template_presets import (
    SUPERMARKET_PRESETS,
    supermarket_density_profile,
    supermarket_visual_config,
)

LAYOUTS = {"promo-4": (2, 2), "promo-6": (2, 3), "promo-9": (3, 3), "promo-12": (3, 4), "promo-16": (4, 4)}
SUPERMARKET_LAYOUTS = {preset["slug"]: (preset["columns"], preset["rows"]) for preset in SUPERMARKET_PRESETS.values()}
DEFAULT_TEMPLATE_SLUG = "promo-4"
DEFAULT_TEMPLATE_NAME = "Premium Market"
PREVIEW_FORMATS = {
    "pdf": (1240, 1754, "A4 portrait"),
    "png": (1240, 1754, "A4 portrait"),
    "instagram_post": (1080, 1080, "1080px 1080px"),
    "instagram_story": (1080, 1920, "1080px 1920px"),
    "whatsapp": (1080, 1920, "1080px 1920px"),
}
LAYOUT_ALIASES = {"premium-market": "promo-4", "compact-weekly": "promo-9"}
UNIT_ALIASES = {
    "l": "L", "lt": "L", "litre": "L", "liter": "L",
    "ml": "mL", "kg": "kg", "g": "g", "gr": "g",
    "adet": "adet", "piece": "adet", "pcs": "adet",
}
LOCALIZED_COPY = {
    "tr": {"offers": "Haftanın Fırsatları", "products": "ürün", "stock": "Stoklarla sınırlıdır.", "image": "Ürün görseli"},
    "en": {"offers": "Weekly offers", "products": "products", "stock": "While stocks last.", "image": "Product image"},
    "fr": {"offers": "Offres de la semaine", "products": "produits", "stock": "Dans la limite des stocks.", "image": "Image du produit"},
    "de": {"offers": "Wochenangebote", "products": "Produkte", "stock": "Nur solange der Vorrat reicht.", "image": "Produktbild"},
}


def render_campaign_preview_html(
    campaign: Campaign,
    template: Template | None,
    *,
    generated_at: datetime,
    output_format: str | None = None,
) -> str:
    payload = _live_payload(campaign, template)
    selected_format = output_format or (payload.get("builder_config") or {}).get("output_format", "pdf")
    html = render_render_payload_html(payload, generated_at=generated_at)
    return _apply_output_format(html, selected_format)


def render_render_payload_html(payload: dict[str, Any], *, generated_at: datetime) -> str:
    config = dict(payload.get("template_config") or {})
    requested_slug = str(payload.get("template_slug") or config.get("layout") or "promo-4")
    family = str(payload.get("layout_family") or requested_slug)
    slug = requested_slug
    if slug in SUPERMARKET_LAYOUTS:
        html = _render_supermarket_payload_html(payload, generated_at=generated_at)
        visual = supermarket_visual_config(config)
        variables = (
            f':root{{--promo-start:{visual["background_start"]};--promo-end:{visual["background_end"]};'
            f'--card-bg:{visual["card_background"]};--card-border:{visual["card_border_color"]};'
            f'--price-panel:{visual["price_panel_background"]};--price-color:{visual["price_color"]};'
            f'--label-bg:{visual["brand_label_background"]}}}'
        )
        html = html.replace("</style></head>", f"</style><style>{variables}{SUPERMARKET_ART_DIRECTION_CSS}</style></head>", 1)
        title_visible = str(visual["show_header_title"]).lower()
        html = html.replace('<header class="hero">', f'<header class="hero" data-title-visible="{title_visible}">', 1)
        subtitle = _text((payload.get("header") or {}).get("promo_title") or "PROMO")
        return html.replace(">PROMO</p>", f">{subtitle}</p>", 1)
    compact = family == "compact-weekly" or slug == "compact-weekly"
    if slug in LAYOUT_ALIASES:
        slug = str(config.get("grid_preset") or LAYOUT_ALIASES[slug])
    if slug not in LAYOUTS:
        slug = {9: "promo-9", 16: "promo-16"}.get(int(config.get("slot_count") or 4), "promo-4")
    items = list(payload.get("items") or [])
    columns, rows = LAYOUTS[slug]
    if len(items) == 1:
        columns, rows = 1, 1
    elif len(items) == 2:
        columns, rows = 2, 1
    elif len(items) == 3:
        columns, rows = 3, 1
    elif len(items) == 4:
        columns, rows = 2, 2
    elif len(items) <= 6:
        columns, rows = 3, 2
    elif len(items) <= 9:
        columns, rows = 3, (len(items) + 2) // 3
    else:
        columns, rows = 4, (len(items) + 3) // 4
    if len(items) > columns * rows and int(payload.get("contract_version") or 1) < 2:
        slug = "promo-9" if len(items) <= 9 else "promo-16"
        columns, rows = LAYOUTS[slug]
    if len(items) > columns * rows:
        raise ValueError(f"{slug} accepts at most {columns * rows} products")
    language = str(payload.get("language") or "tr").lower()[:2]
    copy = LOCALIZED_COPY.get(language, LOCALIZED_COPY["en"])
    layout_key = f"count-{len(items)}" if len(items) <= 4 else ("count-5-6" if len(items) <= 6 else "count-7-9")
    dense = compact or columns == 4
    header = payload.get("header") or {}
    title = payload.get("title") or header.get("promo_title") or "Campaign"
    validity = header.get("validity_text") or generated_at.strftime("%d.%m.%Y")
    cards = f"<!-- {copy['offers']} {len(items)} {copy['products']} -->" + ("".join(_card(item, config, dense, compact) for item in items) or f'<div class="empty-state">{_text("Bu kampanyada henüz ürün bulunmuyor." if language == "tr" else "No products in this campaign yet.")}</div>')
    # The grid height is a page-composition budget; rows are max-content so cards never stretch into it.
    gap, pad, image, grid = ((18, 18, 620, 980) if len(items) == 1 else
                             (18, 16, 360, 820) if len(items) == 2 else
                             (16, 12, 250, 560) if len(items) == 3 else
                             (16, 12, 210, 860) if len(items) == 4 else
                             (14, 10, 180, 980) if len(items) <= 6 else
                             (12, 9, 150, 1160))
    name_size, price_size = ((24, 42) if len(items) == 1 else (20, 34) if len(items) == 2 else (16, 27) if len(items) <= 6 else (14, 24))
    accent = config.get("primary_color") or config.get("accent_color") or "#c1121f"; dark = config.get("accent_dark") or "#003049"; soft = config.get("secondary_color") or config.get("accent_soft_color") or "#fff1f2"
    logos = _logo(header.get("market_logo"), payload.get("market_name") or "LeafletPilot", "market-logo") + "".join(_logo(x, "", "header-logo") for x in (header.get("header_logos") or []))
    payments = "".join(_logo(x, "", "payment-icon") for x in (header.get("payment_icons") or []))
    stock = header.get("stock_message")
    preview_class = "compact-weekly" if compact else "premium-market"
    template_class = "template-compact-weekly" if compact else "template-premium-market"
    footer = (header.get("footer_note") or copy["stock"]) if config.get("show_footer", True) else ""
    return f'''<!-- preview-{preview_class} template-{_attr(payload.get("template_slug") or slug)} {template_class} {layout_key} layout-{columns}x{rows} products-{len(items)} --><!doctype html><html lang="{_attr(language)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{{box-sizing:border-box}}@page{{size:A4 portrait;margin:0}}html,body{{margin:0;width:1240px;height:1754px;background:#fffaf0;color:#16202a;font-family:Arial,Helvetica,sans-serif}}.preview-document{{width:1240px;height:1754px;padding:38px;display:flex;flex-direction:column;overflow:hidden}}.hero{{height:190px;display:flex;justify-content:space-between;padding:24px 28px;border-radius:12px;background:linear-gradient(135deg,{accent},{dark});color:#fff;overflow:hidden}}.logos{{display:flex;gap:8px;align-items:center;height:38px;margin-bottom:10px}}.market-logo,.header-logo,.payment-icon{{max-height:34px;max-width:140px;object-fit:contain;background:#fff;padding:3px;border-radius:4px}}.market-name{{font-size:18px;font-weight:900}}.eyebrow{{margin:0 0 6px;color:#ffe8b7;font-size:13px;font-weight:700;text-transform:uppercase}}h1{{margin:0;font-size:42px;line-height:44px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}}.meta{{max-width:260px;text-align:right;font-size:15px;font-weight:700;overflow-wrap:anywhere}}.validity,.stock{{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere;line-height:17px}}.stock{{margin-top:8px;font-size:12px;line-height:14px}}.section-title{{height:38px;display:flex;justify-content:space-between;align-items:end;margin-top:16px;color:{dark};font-size:20px;font-weight:800}}.product-grid{{height:{grid}px;display:grid;grid-template-columns:repeat({columns},minmax(0,1fr));grid-template-rows:repeat({rows},max-content);align-content:start;align-items:start;gap:{gap}px;margin-top:12px;min-height:0;overflow:hidden}}.product-card{{display:flex;flex-direction:column;align-self:start;min-width:0;height:max-content;min-height:0;padding:{pad}px;border:1px solid #e5e7eb;border-radius:10px;background:#fff;overflow:hidden;box-shadow:0 5px 14px #0f172a14}}.template-compact-weekly .product-card{{border-radius:6px;box-shadow:none;border-top:4px solid {accent}}}.template-premium-market .product-card{{border-radius:18px;box-shadow:0 10px 24px #0f172a1c}}.product-stage{{width:100%;height:{image}px;flex:0 0 {image}px;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:9px;background:#fff}}.product-image,.image-placeholder{{display:block;width:100%;height:100%;object-fit:contain;object-position:center;border-radius:7px;background:#fff}}.product-image.photo{{padding:4px;border:1px solid #eef0f2}}.product-image.cutout{{filter:drop-shadow(0 8px 7px #0f172a20)}}.image-placeholder{{display:flex;align-items:center;justify-content:center;background:{soft};color:#64748b;font-size:12px;font-weight:700}}.product-brand,.product-name,.product-unit,.product-stock{{overflow-wrap:anywhere;word-break:break-word}}.product-brand{{margin:8px 0 0;color:{accent};font-size:10px;line-height:14px;font-weight:800;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}}.product-name{{margin:4px 0 0;font-size:{name_size}px;line-height:1.15;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.product-unit,.product-stock{{margin:4px 0 0;color:#64748b;font-size:11px;line-height:12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.price-row{{display:flex;min-width:0;width:100%;align-items:flex-start;flex-direction:column;gap:4px;margin-top:8px;padding-top:8px;border-top:1px solid #e5e7eb}}.price{{color:{accent};font-size:{price_size}px;line-height:1.05;font-weight:900;display:block;width:100%;min-width:0;max-width:100%;white-space:normal;overflow:hidden;overflow-wrap:anywhere;word-break:break-all}}.price-secondary{{display:flex;align-items:center;gap:6px;max-width:100%;min-height:18px}}.old-price{{color:#64748b;font-size:12px;text-decoration:line-through;white-space:nowrap}}.promo-badge{{padding:3px 6px;border-radius:999px;background:#fef3c7;color:#92400e;font-size:10px;font-weight:800;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.empty-state{{grid-column:1/-1;display:flex;align-items:center;justify-content:center;color:#64748b}}.footer{{height:46px;display:flex;justify-content:space-between;margin-top:auto;padding-top:10px;border-top:1px solid #e5e7eb;color:#64748b;font-size:12px;overflow:hidden}}.footer-note{{height:28px;line-height:14px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}}.payment-icons{{display:flex;gap:6px;align-items:center}}</style></head><body><main class="preview-document preview-{_attr(slug)} {template_class}"><header class="hero"><div><div class="logos">{logos}</div><p class="eyebrow">{_text(header.get("promo_title") or payload.get("template_name") or "Premium Market")}</p><h1 data-clamp-enabled="true" data-clamp-lines="2">{_text(title)}</h1></div><div class="meta"><div class="validity" data-clamp-enabled="true" data-clamp-lines="2">{_text(validity)}</div>{f'<div class="stock" data-clamp-enabled="true" data-clamp-lines="2">{_text(stock)}</div>' if stock else ''}</div></header><div class="section-title"><strong>{_text(copy["offers"])}</strong><span>{len(items)} {_text(copy["products"])}</span></div><section class="product-grid">{cards}</section><footer class="footer"><span class="footer-note" data-clamp-enabled="true" data-clamp-lines="2">{_text(footer)}</span><span class="payment-icons">{payments}</span></footer></main></body></html>'''


def _live_payload(campaign: Campaign, template: Template | None) -> dict[str, Any]:
    config = dict(template.config_json or {}) if template else {}
    market = campaign.market
    builder_config = dict(campaign.builder_config_json or {})
    config = {**dict(getattr(market, "promo_profile_json", None) or {}), **config, **builder_config}
    header = {k: config.get(k) for k in ("market_logo", "header_logos", "payment_icons", "promo_title", "validity_text", "stock_message", "footer_note")}
    header["market_logo"] = header.get("market_logo") or getattr(market, "logo_url", None)
    header["promo_title"] = builder_config.get("subtitle") or header.get("promo_title")
    header["footer_note"] = builder_config.get("footer") or header.get("footer_note")
    configured_layout = config.get("layout") or getattr(template, "slug", None) or "promo-4"
    item_count = len([item for item in campaign.items if item.match_status != "excluded"])
    layout_family = configured_layout if configured_layout in {"premium-market", "compact-weekly"} else None
    if configured_layout not in LAYOUTS and configured_layout not in LAYOUT_ALIASES and configured_layout not in SUPERMARKET_LAYOUTS:
        configured_layout = "promo-9" if item_count <= 9 else "promo-16"
    result = {"contract_version": 2, "template_id": str(template.id) if template else None, "template_version": getattr(template, "version", None), "template_name": getattr(template, "name", None), "template_slug": configured_layout, "layout_family": layout_family, "template_config": config, "campaign_id": str(campaign.id), "market_id": str(campaign.market_id), "title": builder_config.get("headline") or campaign.title, "language": campaign.language, "currency": campaign.currency, "market_name": getattr(market, "name", None), "header": header, "builder_config": builder_config, "items": []}
    for item in sorted((x for x in campaign.items if x.match_status != "excluded"), key=lambda x: (x.sort_order, str(x.id))):
        mp = getattr(item, "_market_product", None) or item.market_product; product = item.product; effective = resolve_effective_product(product, mp)
        global_image = next((i for i in (getattr(product, "images", []) or []) if i.is_primary and getattr(i, "quality_status", None) != "missing"), None)
        market_image = getattr(mp, "image_storage_key", None)
        image = market_image or getattr(global_image, "storage_key", None)
        image_has_alpha = (
            stored_flyer_image_has_alpha(market_image)
            if market_image
            else getattr(global_image, "has_transparent_background", None)
        )
        result["items"].append({"id": str(item.id), "name": item.display_name or item.incoming_name, "resolved_name": effective.name, "brand": getattr(mp, "private_brand_text", None) or getattr(getattr(product, "brand", None), "name", None), "image_key": image, "image_mime_type": getattr(mp, "image_mime_type", None) or getattr(global_image, "mime_type", None) or "image/png", "image_has_alpha": image_has_alpha, "price": _str(item.price), "old_price": _str(item.old_price), "promo_price": _str(getattr(mp, "promo_price", None) or getattr(product, "promo_price", None)), "currency": item.currency or getattr(mp, "currency", None) or campaign.currency, "package_size": getattr(mp, "private_package_size", None) or getattr(product, "package_size", None), "package_type": getattr(mp, "private_package_type", None) or getattr(product, "package_type", None), "unit_label": item.unit_label, "quantity_label": item.quantity_label, "badge": getattr(mp, "badge_text", None) or getattr(product, "badge_text", None), "stock_note": getattr(mp, "stock_note", None), "sort_order": item.sort_order})
    return result


def _card(item: dict[str, Any], config: dict[str, Any], dense: bool, compact: bool = False) -> str:
    unit = _unit_label(item)
    old = f'<span class="old-price">{_text(_money(item.get("old_price"), item.get("currency")))}</span>' if config.get("show_old_price", True) and item.get("old_price") else ""
    badge = f'<span class="promo-badge">{_text(item["badge"])}</span>' if item.get("badge") else ""
    stock = f'<p class="product-stock">{_text(item["stock_note"])}</p>' if item.get("stock_note") else ""
    brand_text, unit_text = _text(item.get("brand")), _text(unit)
    legacy = f'<!-- class="product-brand">{brand_text} --><!-- class="product-unit">{unit_text} -->'
    variant = "compact-card" if compact else "editorial-card"
    return f'<article class="product-card" data-card-variant="{variant}"><div class="product-stage">{_image(item)}</div>{legacy}<p class="product-brand" data-clamp-enabled="true" data-clamp-lines="1">{brand_text}</p><h2 class="product-name" data-clamp-enabled="true" data-clamp-lines="2">{_text(item.get("name") or item.get("resolved_name"))}</h2><p class="product-unit" data-clamp-enabled="true" data-clamp-lines="2">{unit_text}</p>{stock.replace("class=\"product-stock\"", "class=\"product-stock\" data-clamp-enabled=\"true\" data-clamp-lines=\"2\"") if stock else ''}<div class="price-row"><span class="price">{_text(_money(item.get("price") or item.get("promo_price"), item.get("currency")))}</span><span class="price-secondary">{old}{badge}</span></div></article>'


def _image(item: dict[str, Any]) -> str:
    key = item.get("image_key")
    if key:
        try:
            from app.services.rendering import storage_path_for_key
            path = storage_path_for_key(key)
            if path.is_file() and path.stat().st_size:
                presentation = "cutout" if item.get("image_has_alpha") else "photo"
                encoded = base64.b64encode(path.read_bytes()).decode()
                mime_type = _attr(item.get("image_mime_type") or "image/png")
                return (
                    f'<img class="product-image {presentation}" src="data:{mime_type};base64,{encoded}" '
                    f'alt="{_attr(item.get("name"))}">'
                )
        except (OSError, ValueError): pass
    return '<div class="image-placeholder">Ürün görseli</div>'


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
    major, minor, symbol = _money_parts(value, currency)
    if str(currency or "").strip().upper() in {"USD", "GBP", "CHF", "KR"}:
        return f"{symbol} {major}{minor}"
    return f"{major}{minor}{symbol}"
def _text(value: Any) -> str: return escape(str(value or ""), quote=False)
def _attr(value: Any) -> str: return escape(str(value or ""), quote=True)


def _money_parts(value: Any, currency: str | None) -> tuple[str, str, str]:
    if value is None:
        return "-", "", ""
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    major, minor = f"{amount:.2f}".split(".")
    code = str(currency or "").strip().upper()
    symbol = {"EUR": "\u20ac", "TRY": "\u20ba", "USD": "$", "GBP": "\u00a3", "CHF": "CHF", "KR": "kr"}.get(code, str(currency or ""))
    separator = "." if code in {"USD", "CHF", "KR"} else ","
    return major, f"{separator}{minor}", symbol


def _unit_label(item: dict[str, Any]) -> str:
    """Return one canonical package label for preview and every export format."""
    quantity = item.get("quantity_label") or item.get("package_size")
    package_type = item.get("package_type") or item.get("unit_label")
    if not quantity and not package_type:
        return ""
    text = " ".join(str(quantity or "").split())
    if re.search(r"\bx\b", text, re.IGNORECASE):
        return text
    match = re.search(r"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>[A-Za-zÇĞİÖŞÜçğıöşü]+)\s*$", text)
    if match:
        canonical = UNIT_ALIASES.get(match.group("unit").casefold(), match.group("unit"))
        return f"{text[:match.start('unit')].rstrip()} {canonical}".strip()
    if package_type:
        raw_type = str(package_type).strip()
        canonical_type = UNIT_ALIASES.get(raw_type.casefold(), raw_type)
        return f"{text} {canonical_type}".strip()
    return text


def _apply_output_format(html: str, output_format: str | None) -> str:
    selected = output_format if output_format in PREVIEW_FORMATS else "pdf"
    width, height, page_size = PREVIEW_FORMATS[selected]
    html = html.replace("@page{size:A4 portrait;margin:0}", f"@page{{size:{page_size};margin:0}}")
    html = html.replace("width:1240px;height:1754px", f"width:{width}px;height:{height}px")
    html = html.replace("<body>", f'<body data-output-format="{_attr(selected)}" data-preview-width="{width}" data-preview-height="{height}">', 1)
    return html


def _render_supermarket_payload_html(payload: dict[str, Any], *, generated_at: datetime) -> str:
    config = supermarket_visual_config(payload.get("template_config"))
    slug = str(payload.get("template_slug") or "supermarket-promo-4")
    columns, rows = SUPERMARKET_LAYOUTS[slug]
    items = list(payload.get("items") or [])
    if len(items) > 4 and slug == "supermarket-promo-4":
        slug, (columns, rows) = "supermarket-promo-9", SUPERMARKET_LAYOUTS["supermarket-promo-9"]
    if len(items) > 9 and slug != "supermarket-promo-16":
        slug, (columns, rows) = "supermarket-promo-16", SUPERMARKET_LAYOUTS["supermarket-promo-16"]
    if len(items) == 1:
        columns, rows = 1, 1
    elif len(items) == 2:
        columns, rows = 2, 1
    elif len(items) <= 4:
        columns, rows = 2, 2
    limit = columns * rows
    if len(items) > limit:
        raise ValueError(f"{slug} accepts at most {limit} products")
    density = supermarket_density_profile(slug)
    header = payload.get("header") or {}
    title = payload.get("title") or "Campaign"
    validity = header.get("validity_text") or generated_at.strftime("%d.%m.%Y")
    market_fallback = (payload.get("market_name") or "MARKET") if config["show_market_name"] else ""
    logos = _logo(header.get("market_logo"), market_fallback, "market-logo")
    if config.get("show_additional_logos", True):
        logos += "".join(_logo(value, "", "header-logo") for value in (header.get("header_logos") or [])[:2])
    payments = "".join(_logo(value, "", "payment-icon") for value in (header.get("payment_icons") or [])) if config.get("show_payment_icons", True) else ""
    cards = "".join(
        _supermarket_card(item, config, density, index=index) for index, item in enumerate(items)
    )
    stock = header.get("stock_message") if config.get("show_stock_message", True) else ""
    copy = LOCALIZED_COPY.get(str(payload.get("language") or "tr").lower()[:2], LOCALIZED_COPY["en"])
    footer_note = (header.get("footer_note") or copy["stock"]) if config.get("show_footer_note", True) else ""
    stock_html = f'<div class="stock" data-clamp-enabled="true" data-clamp-lines="2">{_text(stock)}</div>' if stock else ""
    title_html = f'<h1 data-clamp-enabled="true" data-clamp-lines="2">{_text(title)}</h1>' if config["show_header_title"] else ""
    footer_html = f'<footer class="footer"><span class="footer-note" data-clamp-enabled="true" data-clamp-lines="1">{_text(footer_note)}</span><span class="payment-icons">{payments}</span></footer>' if config["show_footer"] else ""
    semantic_classes = " ".join((
        f'density-{density["name"]}', f'retail-header-{config["header_style"]}', f'retail-card-{config["card_style"]}',
        f'retail-price-{config["price_style"]}', f'retail-badge-{config["badge_style"]}', f'retail-image-{config["image_treatment"]}',
        f'composition-{density["composition"]}',
    ))
    return f'''<!doctype html><html lang="{_attr(payload.get("language") or "tr")}"><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}@page{{size:A4 portrait;margin:0}}html,body{{margin:0;width:1240px;height:1754px;background:{config["background_end"]};font-family:Arial,Helvetica,sans-serif}}.preview-document{{width:1240px;height:1754px;padding:24px;display:flex;flex-direction:column;overflow:hidden;background:linear-gradient(145deg,{config["background_start"]},{config["background_end"]})}}.hero{{height:{density["header_height"]}px;flex:0 0 {density["header_height"]}px;padding:18px 24px;border-radius:18px;background:linear-gradient(135deg,{config["background_start"]},{config["background_end"]});color:{config["title_color"]};display:flex;justify-content:space-between;overflow:hidden;position:relative}}.retail-header-burst .hero:after{{content:"";position:absolute;right:-100px;top:-130px;width:420px;height:420px;border-radius:50%;background:{config["price_panel_background"]}33}}.retail-header-band .hero{{border-radius:4px;border-bottom:10px solid {config["price_panel_background"]}}}.retail-header-minimal .hero{{border-radius:0;background:{config["background_end"]};border-left:12px solid {config["price_panel_background"]}}}.logos{{display:flex;gap:8px;align-items:center;height:46px;margin-bottom:9px;position:relative;z-index:1}}.market-logo,.header-logo{{max-height:46px;max-width:190px;object-fit:contain;background:transparent;padding:0;border-radius:0}}.header-logo{{max-width:105px;max-height:36px}}.payment-icon{{max-height:26px;max-width:72px;object-fit:contain;background:#fff;padding:3px;border-radius:5px}}.market-name{{font-size:20px;font-weight:1000;letter-spacing:.04em}}.eyebrow{{margin:0 0 4px;color:{config["price_panel_background"]};font-size:17px;font-weight:900;text-transform:uppercase;position:relative;z-index:1}}h1{{margin:0;max-width:760px;font-size:{42 if columns < 4 else 31}px;line-height:1.02;font-weight:1000;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere;position:relative;z-index:1}}.meta{{max-width:285px;text-align:right;font-size:{16 if columns < 4 else 14}px;font-weight:900;position:relative;z-index:1}}.validity,.stock{{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere;line-height:19px}}.stock{{margin-top:8px;color:{config["price_panel_background"]};font-size:13px;line-height:15px}}.section-title{{height:34px;flex:0 0 34px;display:flex;justify-content:space-between;align-items:end;padding:0 4px;color:#fff;font-size:{18 if columns < 4 else 15}px;font-weight:900;text-transform:uppercase}}.product-grid{{height:{density["grid_height"]}px;display:grid;grid-template-columns:repeat({columns},minmax(0,1fr));grid-template-rows:repeat({rows},minmax(0,1fr));gap:{density["grid_gap"]}px;margin-top:{10 if columns < 4 else 8}px;min-height:0;overflow:hidden}}.product-card{{display:flex;flex-direction:column;min-width:0;height:100%;padding:{density["card_padding"]}px;border:2px solid {config["card_border_color"]};border-radius:{density["card_radius"]}px;background:{config["card_background"]};overflow:hidden}}.retail-card-shadow .product-card{{box-shadow:0 6px 0 #5f111944}}.retail-card-outlined .product-card{{box-shadow:none;border-width:3px}}.retail-card-rounded .product-card{{border-radius:{density["card_radius"] + 8}px;box-shadow:0 7px 20px #4c0b1826}}.promo-card-image{{width:100%;height:{density["image_height"]}px;flex:0 0 {density["image_height"]}px;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:11px;background:#fff;margin-bottom:7px}}.retail-image-cutout .promo-card-image{{background:transparent}}.retail-image-photo .promo-card-image{{border:1px solid {config["card_border_color"]}66;padding:4px}}.product-image,.image-placeholder{{display:block;width:100%;height:100%;object-fit:contain;object-position:center;border-radius:9px;background:transparent}}.product-image.photo{{padding:4px;border:1px solid #f3e4c2}}.product-image.cutout{{filter:drop-shadow(0 8px 7px #5f1b1b2b)}}.image-placeholder{{display:flex;align-items:center;justify-content:center;background:#fff1c7;color:#8a5a00;font-size:12px;font-weight:800}}.price-panel{{order:2;margin:0 0 7px;min-height:{density["price_panel_height"]}px;padding:{7 if columns < 4 else 5}px {10 if columns < 4 else 6}px;background:{config["price_panel_background"]};border-radius:9px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,32%);grid-template-areas:"price badge" "price old";align-items:center;gap:2px 5px;overflow:hidden}}.retail-price-ticket .price-panel{{clip-path:polygon(0 0,96% 0,100% 50%,96% 100%,0 100%);padding-right:8%}}.retail-price-split .price-panel{{background:transparent;border:2px solid {config["price_panel_background"]}}}.price{{grid-area:price;color:{config["price_color"]};font-size:{density["price_size"]}px;line-height:.9;font-weight:1000;min-width:0;max-width:100%;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.price-minor{{font-size:.56em;vertical-align:baseline}}.price-currency{{font-size:.42em;margin:0 2px;vertical-align:top}}.old-price{{grid-area:old;color:#6d4b39;font-size:{12 if columns < 4 else 10}px;text-decoration:line-through;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.promo-badge{{grid-area:badge;justify-self:end;max-width:100%;color:#fff;background:{config["brand_label_background"]};padding:4px 6px;border-radius:5px;font-size:{density["badge_size"]}px;line-height:1;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.retail-badge-pill .promo-badge{{border-radius:999px}}.retail-badge-burst .promo-badge{{clip-path:polygon(50% 0,62% 18%,82% 8%,87% 31%,100% 42%,84% 57%,91% 80%,67% 82%,55% 100%,41% 82%,18% 91%,14% 66%,0 54%,17% 38%,9% 16%,35% 18%);padding:9px 8px}}.retail-badge-ribbon .promo-badge{{border-radius:2px;transform:rotate(-2deg)}}.brand-label{{order:3;align-self:flex-start;max-width:100%;padding:3px 8px;border-radius:5px;background:{config["brand_label_background"]};color:{config["brand_label_color"]};font-size:{11 if columns < 4 else 9}px;line-height:1.1;font-weight:900;text-transform:uppercase;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.product-name{{order:4;margin:5px 0 0;color:{config["product_title_color"]};font-size:{density["name_size"]}px;line-height:1.08;font-weight:900;display:-webkit-box;-webkit-line-clamp:{density["name_lines"]};-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}}.product-unit{{order:5;margin:3px 0 0;color:{config["product_title_color"]};font-size:{density["unit_size"]}px;line-height:1.1;font-weight:800;overflow:hidden;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical}}.footer{{height:{density["footer_height"]}px;flex:0 0 {density["footer_height"]}px;display:flex;justify-content:space-between;align-items:center;color:#fff;font-size:11px;font-weight:700;overflow:hidden}}.footer-note{{max-width:68%;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}}.payment-icons{{display:flex;gap:5px;align-items:center}}</style></head><body><main class="preview-document preview-{_attr(slug)} {_attr(semantic_classes)}" data-density-profile="{_attr(density["name"])}" data-layout="{columns}x{rows}"><header class="hero"><div><div class="logos">{logos}</div><p class="eyebrow">PROMO</p>{title_html}</div><div class="meta"><div class="validity" data-clamp-enabled="true" data-clamp-lines="2">{_text(validity)}</div>{stock_html}</div></header><div class="section-title"><span>{_text(copy["offers"])}</span><span>{len(items)} {_text(copy["products"])}</span></div><section class="product-grid">{cards}</section>{footer_html}</main></body></html>'''


def _supermarket_card(item: dict[str, Any], config: dict[str, Any], density: dict[str, Any], *, index: int) -> str:
    major, minor, symbol = _money_parts(item.get("price") or item.get("promo_price"), item.get("currency"))
    prefix_currency = str(item.get("currency") or "").strip().upper() in {"USD", "GBP", "CHF", "KR"}
    unit = _unit_label(item)
    old = f'<span class="old-price">{_text(_money(item.get("old_price"), item.get("currency")))}</span>' if config["show_old_price"] and item.get("old_price") else ""
    badge = f'<span class="promo-badge">{_text(item["badge"])}</span>' if config["show_discount_badge"] and item.get("badge") else ""
    brand = _text(item.get("brand"))
    currency_html = f'<span class="price-currency">{_text(symbol)}</span>'
    price = f'{currency_html}<span class="price-major">{_text(major)}</span><span class="price-minor">{_text(minor)}</span>' if prefix_currency else f'<span class="price-major">{_text(major)}</span><span class="price-minor">{_text(minor)}</span>{currency_html}'
    image_stage = "cutout" if item.get("image_has_alpha") else ("photo" if item.get("image_key") else "fallback")
    image = f'<div class="promo-card-image" data-image-stage="{image_stage}">{_image(item)}</div>' if config["show_product_image"] else ""
    brand_html = f'<span class="brand-label">{brand}</span>' if brand else ""
    name = f'<h2 class="product-name" data-clamp-enabled="true" data-clamp-lines="{density["name_lines"]}">{_text(item.get("name") or item.get("resolved_name"))}</h2>' if config["show_product_name"] else ""
    package = f'<p class="product-unit" data-clamp-enabled="true" data-clamp-lines="1">{_text(unit)}</p>' if config["show_package_size"] else ""
    emphasis = "featured" if density["name"] == "editorial" and (item.get("emphasis") == "featured" or index == 0) else "normal"
    rhythm = ("a", "b", "c")[index % 3]
    price_class = "price price-long" if len(major) + len(symbol) >= 8 else "price"
    return (
        f'<article class="product-card" data-emphasis="{emphasis}" data-rhythm="{rhythm}">{image}<div class="price-panel"><span class="{price_class}">{price}</span>{badge}{old}</div>{brand_html}{name}{package}</article>'
    )

SUPERMARKET_ART_DIRECTION_CSS = """
.preview-document{position:relative;background:linear-gradient(150deg,var(--promo-start,#ef3b24),var(--promo-end,#a40e1a))}
.hero{border-radius:8px;background:transparent;border-bottom:2px solid #ffffff55}
.retail-header-burst .hero{padding-left:34px;background:linear-gradient(110deg,#ffffff16,transparent 62%)}
.retail-header-burst .hero:before{content:"";position:absolute;left:-70px;bottom:-150px;width:310px;height:310px;border-radius:50%;background:var(--price-panel,#ffd928);opacity:.2}
.retail-header-burst .hero:after{right:-72px;top:-190px;width:470px;height:470px;background:var(--price-panel,#ffd928);opacity:.24}
.retail-header-band .hero{border:0;border-radius:0;border-top:14px solid var(--price-panel,#ffd928);border-bottom:14px solid var(--price-panel,#ffd928);background:var(--promo-end,#a40e1a)}
.retail-header-band .eyebrow{display:inline-block;padding:4px 14px;color:var(--promo-end,#a40e1a);background:var(--price-panel,#ffd928)}
.retail-header-minimal .hero{border:0;border-left:14px solid var(--price-panel,#ffd928);background:#00000013}
.retail-header-minimal .eyebrow{color:#fff;letter-spacing:.18em}
.section-title{position:relative;border-bottom:1px solid #ffffff70;letter-spacing:.08em}
.product-grid{position:relative}
.product-card{position:relative;border:0;border-bottom:1px solid color-mix(in srgb,var(--card-border,#f1b900) 48%,transparent);border-radius:8px;background:color-mix(in srgb,var(--card-bg,#fff8e7) 93%,transparent);box-shadow:none}
.retail-card-shadow .product-card{border:0;background:color-mix(in srgb,var(--card-bg,#fff8e7) 94%,transparent);box-shadow:0 10px 24px #4b08152b}
.retail-card-outlined .product-card{border:1px solid color-mix(in srgb,var(--card-border,#f1b900) 58%,transparent);border-radius:3px;background:color-mix(in srgb,var(--card-bg,#fff8e7) 84%,transparent);box-shadow:none}
.retail-card-rounded .product-card{border:0;border-radius:28px;background:var(--card-bg,#fff8e7);box-shadow:0 8px 20px #4c0b1822}
.promo-card-image{border:0;border-radius:10px;background:color-mix(in srgb,var(--card-bg,#fff8e7) 30%,transparent);overflow:visible}
.retail-image-stage .promo-card-image{background:radial-gradient(circle at 50% 70%,#ffffffb8 0,#ffffff42 44%,transparent 72%)}
.retail-image-cutout .promo-card-image,.promo-card-image[data-image-stage="cutout"]{background:transparent}
.retail-image-photo .promo-card-image,.promo-card-image[data-image-stage="photo"]{padding:7px;border:1px solid #ffffff90;background:#fff}
.product-image.photo{padding:3px;border:0;border-radius:8px;background:#fff}
.product-image.cutout{filter:drop-shadow(0 12px 10px #4b071f38)}
.image-placeholder{border:1px dashed color-mix(in srgb,var(--card-border,#f1b900) 65%,transparent);border-radius:8px;background:color-mix(in srgb,var(--card-bg,#fff8e7) 76%,transparent)}
.price-panel{align-self:flex-start;width:88%;border:0;border-radius:4px;box-shadow:5px 5px 0 #8e101c20}
.product-card[data-rhythm="b"] .price-panel{align-self:flex-end}
.product-card[data-rhythm="c"] .price-panel{width:82%}
.retail-price-panel .price-panel{border-left:9px solid color-mix(in srgb,var(--price-color,#c5161d) 72%,transparent)}
.retail-price-ticket .price-panel{width:92%;border-radius:0;box-shadow:7px 7px 0 #6f10212b}
.retail-price-split .price-panel{width:100%;border:3px solid var(--price-panel,#ffd928);border-left:12px solid var(--price-panel,#ffd928);background:color-mix(in srgb,var(--card-bg,#fff8e7) 68%,transparent);box-shadow:none}
.price{overflow:hidden;text-overflow:clip;font-variant-numeric:tabular-nums;letter-spacing:-.035em}
.price.price-long{font-size:.72em;letter-spacing:-.055em}
.price-minor{font-weight:900}
.price-currency{font-weight:900;letter-spacing:0}
.promo-badge{padding:7px 9px;border:2px solid #fff7;box-shadow:0 4px 0 #630d1740;text-align:center}
.retail-badge-pill .promo-badge{border-radius:999px}
.retail-badge-sticker .promo-badge{border-radius:7px;transform:rotate(-3deg)}
.retail-badge-burst .promo-badge{min-width:62px;min-height:56px;display:grid;place-items:center;padding:11px 8px}
.retail-badge-ribbon .promo-badge{margin-right:-8px;padding:7px 13px;border:0;border-radius:0;clip-path:polygon(0 0,100% 0,91% 50%,100% 100%,0 100%,7% 50%)}
.brand-label{padding:0;background:transparent;color:var(--label-bg,#c5161d);border-radius:0;letter-spacing:.08em}
.product-name{margin-top:6px;letter-spacing:-.012em}
.product-unit{opacity:.72;font-weight:700}
.footer{border-top:1px solid #ffffff66}
.composition-hero-offers .product-card{border:0;background:color-mix(in srgb,var(--card-bg,#fff8e7) 82%,transparent)}
.composition-hero-offers .product-card[data-emphasis="featured"]{background:var(--card-bg,#fff8e7);box-shadow:0 13px 28px #4b071f35}
.composition-hero-offers .product-card[data-emphasis="featured"] .promo-card-image{height:448px;flex-basis:448px}
.composition-hero-offers .product-card[data-emphasis="featured"] .price{font-size:62px}
.composition-hero-offers .product-card[data-emphasis="featured"] .promo-badge{font-size:20px}
.composition-hero-offers .product-card:not([data-emphasis="featured"]) .promo-card-image{height:414px;flex-basis:414px}
.composition-hero-offers .price-panel{width:94%;border-radius:3px}
.composition-weekly-grid .product-card{border-radius:6px}
.composition-weekly-grid .promo-card-image{margin-bottom:5px}
.composition-catalogue-grid .product-card{border-right:1px solid color-mix(in srgb,var(--card-border,#f1b900) 34%,transparent);border-bottom:1px solid color-mix(in srgb,var(--card-border,#f1b900) 34%,transparent);border-radius:0;background:color-mix(in srgb,var(--card-bg,#fff8e7) 88%,transparent)}
.composition-catalogue-grid .price-panel{width:94%;box-shadow:3px 3px 0 #6f102119}
.composition-catalogue-grid .brand-label{font-size:8px}
.density-editorial .product-card .price.price-long{font-size:40px}
.density-weekly .product-card .price.price-long{font-size:27px}
.density-compact .product-card .price.price-long{font-size:20px}
.composition-hero-offers .product-grid{gap:28px}
.composition-hero-offers.retail-card-shadow .product-card{border:0;background:transparent;box-shadow:none}
.composition-hero-offers.retail-card-shadow .product-card[data-emphasis="featured"]{background:radial-gradient(circle at 48% 42%,#ffffff24,transparent 68%);box-shadow:none}
.composition-hero-offers.retail-card-shadow .product-name,.composition-hero-offers.retail-card-shadow .product-unit{color:#fff;text-shadow:0 1px 1px #4f071f66}
.composition-hero-offers.retail-card-shadow .brand-label{color:var(--price-panel,#ffd928)}
.composition-hero-offers .product-card[data-rhythm="b"] .price-panel{width:82%}
.composition-hero-offers .product-card[data-rhythm="c"] .price-panel{width:76%}
.composition-weekly-grid .product-grid{gap:0;padding:9px;border-radius:5px;background:color-mix(in srgb,var(--card-bg,#fff8e7) 92%,transparent)}
.composition-weekly-grid.retail-card-shadow .product-card{border:0;border-right:1px solid color-mix(in srgb,var(--card-border,#f1b900) 36%,transparent);border-bottom:1px solid color-mix(in srgb,var(--card-border,#f1b900) 36%,transparent);border-radius:0;background:transparent;box-shadow:none}
.composition-weekly-grid .product-card:nth-child(3n){border-right:0}
.composition-weekly-grid .product-card:nth-last-child(-n+3){border-bottom:0}
.composition-catalogue-grid .product-grid{gap:0;padding:6px;border-radius:3px;background:color-mix(in srgb,var(--card-bg,#fff8e7) 90%,transparent)}
.composition-catalogue-grid.retail-card-shadow .product-card{border:0;border-right:1px solid color-mix(in srgb,var(--card-border,#f1b900) 38%,transparent);border-bottom:1px solid color-mix(in srgb,var(--card-border,#f1b900) 38%,transparent);background:transparent;box-shadow:none}
.composition-catalogue-grid .product-card:nth-child(4n){border-right:0}
.composition-catalogue-grid .product-card:nth-last-child(-n+4){border-bottom:0}
.composition-weekly-grid.retail-card-outlined .product-card,.composition-catalogue-grid.retail-card-outlined .product-card{border:1px solid color-mix(in srgb,var(--card-border,#f1b900) 58%,transparent);background:#ffffff28}
.composition-weekly-grid.retail-card-rounded .product-card,.composition-catalogue-grid.retail-card-rounded .product-card{margin:3px;border:0;border-radius:18px;background:#ffffff55;box-shadow:0 5px 13px #4c0b1820}
"""
