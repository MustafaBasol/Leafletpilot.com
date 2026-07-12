from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.models.market import Market


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


STARTER = PlanCapabilities(True, 25, False, True, False, 0, False, 1, 10)
GROWTH = PlanCapabilities(True, 250, True, True, True, 5, False, 3, 50)
PRO = PlanCapabilities(True, None, True, True, True, None, True, None, 250)
UNASSIGNED = PlanCapabilities(True, 0, False, True, False, 0, False, 1, 10)

PLAN_CAPABILITIES: Final[dict[str, PlanCapabilities]] = {
    "starter": STARTER,
    "growth": GROWTH,
    "pro": PRO,
    "unassigned": UNASSIGNED,
}


def resolve_plan_code(market: Market | None) -> str:
    plan_code = (market.subscription_plan if market is not None else None) or "unassigned"
    return plan_code if plan_code in PLAN_CAPABILITIES else "unassigned"


def resolve_capabilities(market: Market | None) -> PlanCapabilities:
    return PLAN_CAPABILITIES[resolve_plan_code(market)]


def require_capability(market: Market, capability: str) -> None:
    from fastapi import HTTPException, status

    if not getattr(resolve_capabilities(market), capability, False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"The current plan does not include {capability.replace('_', ' ')}.",
        )


def has_capacity(current_count: int, limit: int | None) -> bool:
    return limit is None or current_count < limit
