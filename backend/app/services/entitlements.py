from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.models.market import Market
from app.services.plans import (
    KNOWN_RAW_PLAN_CODES,
    PLAN_REGISTRY,
    PlanDefinition,
    normalize_plan_code,
    plan_rank,
)


@dataclass(frozen=True)
class PlanCapabilities:
    global_catalog_access: bool
    private_products_limit: int | None
    product_image_override: bool
    global_templates: bool
    clone_global_template: bool
    private_templates_limit: int | None
    custom_template: bool
    branding_assets_limit: int | None
    monthly_exports_limit: int | None
    monthly_campaigns_limit: int | None
    export_formats: tuple[str, ...]


def _capabilities_from_plan(plan: PlanDefinition) -> PlanCapabilities:
    return PlanCapabilities(
        global_catalog_access=plan.global_catalog_access,
        private_products_limit=plan.private_products_limit,
        product_image_override=plan.product_image_override,
        global_templates=plan.global_templates,
        clone_global_template=plan.clone_global_template,
        private_templates_limit=plan.private_templates_limit,
        custom_template=plan.custom_template,
        branding_assets_limit=plan.branding_assets_limit,
        monthly_exports_limit=plan.monthly_exports_limit,
        monthly_campaigns_limit=plan.monthly_campaigns_limit,
        export_formats=plan.export_formats,
    )


# Keyed by every raw/persisted code (canonical + legacy aliases like "growth")
# so existing direct dict lookups keep working.
PLAN_CAPABILITIES: Final[dict[str, PlanCapabilities]] = {
    raw_code: _capabilities_from_plan(PLAN_REGISTRY[normalize_plan_code(raw_code)]) for raw_code in KNOWN_RAW_PLAN_CODES
} | {"unassigned": _capabilities_from_plan(PLAN_REGISTRY["unassigned"])}

STARTER = PLAN_CAPABILITIES["starter"]
GROWTH = PLAN_CAPABILITIES["growth"]
PRO = PLAN_CAPABILITIES["pro"]
UNASSIGNED = PLAN_CAPABILITIES["unassigned"]


def resolve_plan_code(market: Market | None) -> str:
    """Return the raw/display plan code (preserves legacy codes like "growth")."""
    plan_code = (market.subscription_plan if market is not None else None) or "unassigned"
    return plan_code if plan_code in PLAN_CAPABILITIES else "unassigned"


def resolve_capabilities(market: Market | None) -> PlanCapabilities:
    raw_code = resolve_plan_code(market)
    return PLAN_CAPABILITIES.get(raw_code) or _capabilities_from_plan(PLAN_REGISTRY[normalize_plan_code(raw_code)])


def resolve_plan_rank(market: Market | None) -> int:
    return plan_rank(resolve_plan_code(market))


def require_capability(market: Market, capability: str) -> None:
    from fastapi import HTTPException, status

    if not getattr(resolve_capabilities(market), capability, False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Mevcut abonelik planı bu yeteneği desteklemiyor: {capability.replace('_', ' ')}.",
        )


def require_export_format(market: Market, requested_format: str) -> None:
    from fastapi import HTTPException, status

    if requested_format not in resolve_capabilities(market).export_formats:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Mevcut abonelik planı '{requested_format}' çıktı formatını desteklemiyor.",
        )


def has_capacity(current_count: int, limit: int | None) -> bool:
    return limit is None or current_count < limit
