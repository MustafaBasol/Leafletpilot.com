from app.models import Market
from app.services.entitlements import (
    PLAN_CAPABILITIES,
    require_export_format,
    resolve_capabilities,
    resolve_plan_code,
    resolve_plan_rank,
)
from app.services.plans import (
    CANONICAL_PLAN_CODES,
    normalize_plan_code,
    plan_rank,
    public_plans,
)
import pytest
from fastapi import HTTPException


def test_canonical_plan_codes_are_starter_standard_pro() -> None:
    assert CANONICAL_PLAN_CODES == ("starter", "standard", "pro")


def test_growth_normalizes_to_standard_for_capability_and_rank_lookup() -> None:
    assert normalize_plan_code("growth") == "standard"
    assert plan_rank("growth") == plan_rank("standard") == 1
    assert plan_rank("starter") == 0
    assert plan_rank("pro") == 2


def test_unknown_or_missing_plan_code_normalizes_to_unassigned() -> None:
    assert normalize_plan_code(None) == "unassigned"
    assert normalize_plan_code("enterprise") == "unassigned"


def test_resolve_plan_code_preserves_raw_legacy_code_for_display() -> None:
    # Display code stays "growth" (existing markets/tests depend on this),
    # even though capability lookups resolve it to the "standard" definition.
    assert resolve_plan_code(Market(subscription_plan="growth")) == "growth"
    assert resolve_plan_rank(Market(subscription_plan="growth")) == 1


def test_growth_and_standard_share_identical_capabilities() -> None:
    assert PLAN_CAPABILITIES["growth"] == PLAN_CAPABILITIES["standard"]


def test_public_plans_returns_three_public_plans_in_display_order_with_standard_recommended() -> None:
    plans = public_plans()
    assert [plan.code for plan in plans] == ["starter", "standard", "pro"]
    assert [plan.monthly_price for plan in plans] == [59, 119, 199]
    recommended = [plan for plan in plans if plan.is_recommended]
    assert [plan.code for plan in recommended] == ["standard"]


def test_unassigned_plan_is_not_public() -> None:
    assert "unassigned" not in {plan.code for plan in public_plans()}


def test_commercial_campaign_quotas_match_contract() -> None:
    assert resolve_capabilities(Market(subscription_plan="starter")).monthly_campaigns_limit == 4
    assert resolve_capabilities(Market(subscription_plan="standard")).monthly_campaigns_limit == 10
    assert resolve_capabilities(Market(subscription_plan="growth")).monthly_campaigns_limit == 10
    assert resolve_capabilities(Market(subscription_plan="pro")).monthly_campaigns_limit is None


def test_only_real_render_formats_are_ever_offered() -> None:
    for code in ("starter", "standard", "pro"):
        assert set(resolve_capabilities(Market(subscription_plan=code)).export_formats) == {"pdf", "png"}


def test_require_export_format_rejects_unsupported_format() -> None:
    market = Market(subscription_plan="starter")
    require_export_format(market, "pdf")
    with pytest.raises(HTTPException) as exc:
        require_export_format(market, "instagram")
    assert exc.value.status_code == 403


def test_pro_is_the_only_plan_with_true_custom_template_capability() -> None:
    assert resolve_capabilities(Market(subscription_plan="starter")).custom_template is False
    assert resolve_capabilities(Market(subscription_plan="standard")).custom_template is False
    assert resolve_capabilities(Market(subscription_plan="growth")).custom_template is False
    assert resolve_capabilities(Market(subscription_plan="pro")).custom_template is True


def test_standard_can_still_clone_global_templates() -> None:
    assert resolve_capabilities(Market(subscription_plan="standard")).clone_global_template is True
    assert resolve_capabilities(Market(subscription_plan="growth")).clone_global_template is True
    assert resolve_capabilities(Market(subscription_plan="starter")).clone_global_template is False
