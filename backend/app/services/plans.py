"""Canonical commercial plan registry.

Single source of truth for pricing, quotas, and entitlement capabilities.
`entitlements.py` derives its capability dataclass from this registry instead
of maintaining a second copy; the landing page and platform admin consume the
same data through the public/platform APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Canonical plan codes. "growth" is a legacy code that is still persisted on
# existing Market rows and written by some seed/test fixtures; it resolves to
# "standard" everywhere capabilities or ranking are evaluated, but the raw
# value is preserved for display (see entitlements.resolve_plan_code).
CANONICAL_PLAN_CODES: Final[tuple[str, ...]] = ("starter", "standard", "pro")
LEGACY_PLAN_ALIASES: Final[dict[str, str]] = {"growth": "standard"}
KNOWN_RAW_PLAN_CODES: Final[tuple[str, ...]] = (*CANONICAL_PLAN_CODES, *LEGACY_PLAN_ALIASES.keys())

TEMPLATE_POLICY_LIMITED = "limited"
TEMPLATE_POLICY_ALL = "all"
TEMPLATE_POLICY_ALL_PLUS_CUSTOM = "all_plus_custom"


@dataclass(frozen=True)
class PlanDefinition:
    code: str
    name: str
    monthly_price: float | None
    currency: str
    tagline: str
    monthly_campaigns_limit: int | None
    private_products_limit: int | None
    template_policy: str
    starter_template_count: int
    custom_template: bool
    clone_global_template: bool
    branding_assets_limit: int | None
    product_image_override: bool
    export_formats: tuple[str, ...]
    support_tier: str
    global_catalog_access: bool
    telegram_enabled: bool
    global_templates: bool
    private_templates_limit: int | None
    monthly_exports_limit: int | None
    is_public: bool
    is_recommended: bool
    display_order: int
    features: tuple[str, ...]


STARTER = PlanDefinition(
    code="starter",
    name="Başlangıç",
    monthly_price=59,
    currency="EUR",
    tagline="Tek şubeli küçük marketler için",
    monthly_campaigns_limit=4,
    private_products_limit=25,
    template_policy=TEMPLATE_POLICY_LIMITED,
    starter_template_count=2,
    custom_template=False,
    clone_global_template=False,
    branding_assets_limit=1,
    product_image_override=False,
    export_formats=("pdf", "png"),
    support_tier="standard",
    global_catalog_access=True,
    telegram_enabled=True,
    global_templates=True,
    private_templates_limit=0,
    monthly_exports_limit=10,
    is_public=True,
    is_recommended=False,
    display_order=1,
    features=("Ayda 4 kampanya", "2 broşür şablonu", "A4 PDF + PNG çıktı", "Telegram üzerinden kullanım"),
)

STANDARD = PlanDefinition(
    code="standard",
    name="Plus",
    monthly_price=119,
    currency="EUR",
    tagline="Büyüyen ve düzenli kampanya yapan marketler için",
    monthly_campaigns_limit=10,
    private_products_limit=250,
    template_policy=TEMPLATE_POLICY_ALL,
    starter_template_count=2,
    custom_template=False,
    clone_global_template=True,
    branding_assets_limit=3,
    product_image_override=True,
    export_formats=("pdf", "png"),
    support_tier="priority",
    global_catalog_access=True,
    telegram_enabled=True,
    global_templates=True,
    private_templates_limit=5,
    monthly_exports_limit=50,
    is_public=True,
    is_recommended=True,
    display_order=2,
    features=("Ayda 10 kampanya", "Tüm broşür şablonları", "A4 PDF + PNG çıktı", "Öncelikli destek"),
)

PRO = PlanDefinition(
    code="pro",
    name="Pro",
    monthly_price=199,
    currency="EUR",
    tagline="Zincir ve yoğun kullanım için",
    monthly_campaigns_limit=None,
    private_products_limit=None,
    template_policy=TEMPLATE_POLICY_ALL_PLUS_CUSTOM,
    starter_template_count=2,
    custom_template=True,
    clone_global_template=True,
    branding_assets_limit=None,
    product_image_override=True,
    export_formats=("pdf", "png"),
    support_tier="phone",
    global_catalog_access=True,
    telegram_enabled=True,
    global_templates=True,
    private_templates_limit=None,
    monthly_exports_limit=250,
    is_public=True,
    is_recommended=False,
    display_order=3,
    features=("Sınırsız kampanya", "Özel şablon çalışması", "Tüm çıktı formatları", "Telefonla destek"),
)

UNASSIGNED = PlanDefinition(
    code="unassigned",
    name="Atanmamış",
    monthly_price=None,
    currency="EUR",
    tagline="",
    monthly_campaigns_limit=0,
    private_products_limit=0,
    template_policy=TEMPLATE_POLICY_LIMITED,
    starter_template_count=0,
    custom_template=False,
    clone_global_template=False,
    branding_assets_limit=1,
    product_image_override=False,
    export_formats=("pdf", "png"),
    support_tier="standard",
    global_catalog_access=True,
    telegram_enabled=False,
    global_templates=True,
    private_templates_limit=0,
    monthly_exports_limit=10,
    is_public=False,
    is_recommended=False,
    display_order=99,
    features=(),
)

PLAN_REGISTRY: Final[dict[str, PlanDefinition]] = {
    "starter": STARTER,
    "standard": STANDARD,
    "pro": PRO,
    "unassigned": UNASSIGNED,
}

PLAN_RANK: Final[dict[str, int]] = {"starter": 0, "standard": 1, "pro": 2}


def normalize_plan_code(raw_code: str | None) -> str:
    """Resolve a raw/persisted plan code to a canonical registry key."""
    if not raw_code:
        return "unassigned"
    resolved = LEGACY_PLAN_ALIASES.get(raw_code, raw_code)
    return resolved if resolved in PLAN_REGISTRY else "unassigned"


def get_plan(raw_code: str | None) -> PlanDefinition:
    return PLAN_REGISTRY[normalize_plan_code(raw_code)]


def plan_rank(raw_code: str | None) -> int:
    return PLAN_RANK.get(normalize_plan_code(raw_code), 0)


def is_valid_assignable_plan_code(code: str) -> bool:
    """Codes a platform admin may assign to a market: canonical + legacy alias."""
    return code in KNOWN_RAW_PLAN_CODES


def public_plans() -> list[PlanDefinition]:
    return sorted((plan for plan in PLAN_REGISTRY.values() if plan.is_public), key=lambda plan: plan.display_order)
