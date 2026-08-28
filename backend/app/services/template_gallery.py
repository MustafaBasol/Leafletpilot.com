"""User-facing metadata and deterministic cached renderer previews; never uses AI."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from app.models import Campaign, CampaignItem, Market, Template
from app.services.preview_renderer import render_campaign_preview_html
from app.services.rendering import render_html_to_png, storage_path_for_key

@dataclass(frozen=True)
class TemplateSuitability:
    minimum: int
    maximum: int
    description: str
    category: str

_BUILTIN = {"compact-weekly": TemplateSuitability(6, 12, "Haftalık kampanyalar için dengeli ve sade tasarım.", "Haftalık"), "premium-market": TemplateSuitability(1, 4, "Az ürünlü, görsel ağırlıklı kampanyalar için.", "Premium"), "supermarket-promo-4": TemplateSuitability(1, 4, "Az sayıdaki ürünü büyük ve dikkat çekici göstermek için.", "Görsel ağırlıklı"), "supermarket-promo-9": TemplateSuitability(5, 9, "Orta büyüklükte kampanyalar için dengeli ürün yerleşimi.", "Dengeli"), "supermarket-promo-16": TemplateSuitability(10, 16, "Çok ürünlü kampanyaları tek sayfada düzenli göstermek için.", "Çok ürünlü")}
_DEMO = (("Nutella", "400 g", "3.49", "4.29"), ("Coca-Cola", "1,5 L", "1.79", "2.39"), ("Tam Yağlı Süt", "1 L", "1.19", "1.49"), ("Çikolatalı Bisküvi", "184 g", "1.99", "2.59"), ("Filtre Kahve", "500 g", "5.99", "7.49"), ("Portakallı Gazoz", "1 L", "1.29", "1.69"), ("Patates Cipsi", "150 g", "2.29", "2.99"), ("Burgu Makarna", "500 g", "1.49", "1.89"), ("Sıvı Deterjan", "1,5 L", "6.99", "8.99"), ("Zeytinyağı", "1 L", "8.49", "10.99"), ("Yoğurt", "750 g", "2.19", "2.79"), ("Elma Suyu", "1 L", "1.59", "1.99"), ("Ton Balığı", "3 x 80 g", "4.79", "5.99"), ("Kaşar Peyniri", "400 g", "4.99", "6.29"), ("Domates Sosu", "700 g", "1.69", "2.19"), ("Tuvalet Kâğıdı", "12'li", "5.99", "7.99"))

def suitability_for_template(slug: str | None, config: dict[str, Any] | None) -> TemplateSuitability:
    key, config = str(slug or "").lower(), dict(config or {})
    if key in _BUILTIN: return _BUILTIN[key]
    slots = int(config.get("slot_count") or 0)
    if slots <= 0: return TemplateSuitability(1, 16, "Farklı kampanya ihtiyaçlarına uyarlanabilir tasarım.", "Esnek")
    if slots <= 4: return TemplateSuitability(1, slots, "Az sayıdaki ürünü öne çıkarmak için.", "Görsel ağırlıklı")
    if slots <= 9: return TemplateSuitability(max(1, slots - 4), slots, "Orta büyüklükte kampanyalar için dengeli yerleşim.", "Dengeli")
    return TemplateSuitability(max(1, slots - 6), slots, "Çok ürünlü kampanyaları düzenli göstermek için.", "Çok ürünlü")

def recommendation_for(templates: list[Template], product_count: int | None, default_template_id: object | None = None) -> Template | None:
    active = [item for item in templates if item.is_active and item.status not in {"draft", "archived"}]
    if not active: return None
    if product_count is None: return next((item for item in active if item.id == default_template_id), active[0])
    def rank(item: Template):
        fit = suitability_for_template(item.slug, item.config_json)
        return (0 if fit.minimum <= product_count <= fit.maximum else 1, abs(((fit.minimum + fit.maximum) / 2) - product_count), item.name.casefold())
    return sorted(active, key=rank)[0]

def demo_item_count(template: Template) -> int: return min(len(_DEMO), suitability_for_template(template.slug, template.config_json).maximum)

def build_demo_campaign(template: Template) -> Campaign:
    market = Market(id=uuid4(), name="LeafletPilot Market", slug="leafletpilot-demo", currency="EUR", language="tr")
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)
    campaign = Campaign(id=uuid4(), market_id=market.id, title="Haftanın Fırsatları", language="tr", currency="EUR", items=[])
    campaign.market = market
    campaign.items = [CampaignItem(id=uuid4(), campaign_id=campaign.id, market_id=market.id, raw_line=name, incoming_name=name, display_name=name, price=Decimal(price), old_price=Decimal(old), currency="EUR", quantity_label=size, sort_order=index, match_status="matched", created_at=timestamp) for index, (name, size, price, old) in enumerate(_DEMO[:demo_item_count(template)])]
    return campaign

def preview_cache_key(template: Template) -> str:
    source = json.dumps({"id": str(template.id), "version": template.version, "name": template.name, "config": template.config_json or {}}, sort_keys=True, ensure_ascii=False, default=str)
    scope = "global" if template.is_global else f"markets/{template.market_id}"
    return f"template-previews/{scope}/{template.id}/{sha256(source.encode('utf-8')).hexdigest()[:16]}.png"

async def generated_preview_path(template: Template) -> Path:
    path = storage_path_for_key(preview_cache_key(template))
    if path.is_file(): return path
    path.parent.mkdir(parents=True, exist_ok=True)
    html = render_campaign_preview_html(build_demo_campaign(template), template, generated_at=datetime(2025, 1, 1, tzinfo=UTC))
    await render_html_to_png(html, path)
    return path