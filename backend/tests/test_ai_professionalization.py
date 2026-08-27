from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.ai import AIProfessionalizationPlanEnvelope
from app.services.ai.professionalization import AIProfessionalizationService, frozen_snapshot_hash
from app.services.campaign_rendering import build_campaign_render_payload


def approved_snapshot():
    return {
        "approved_revision": 4,
        "language": "tr",
        "items": [
            {"name": "First", "price": "1.99", "sort_order": 0},
            {"name": "Second", "price": "2.99", "sort_order": 1},
        ],
    }


def approved_campaign(snapshot=None):
    return SimpleNamespace(
        frozen_at=datetime.now(UTC),
        finalized_at=datetime.now(UTC),
        approved_revision=4,
        snapshot_json=snapshot or approved_snapshot(),
    )


def test_frozen_snapshot_hash_is_canonical_and_excludes_its_marker():
    first = approved_snapshot()
    second = {"items": first["items"], "language": "tr", "approved_revision": 4}
    first["snapshot_sha256"] = "old-marker"

    assert frozen_snapshot_hash(first) == frozen_snapshot_hash(second)


@pytest.mark.parametrize("attribute, value", [("finalized_at", None), ("approved_revision", None)])
def test_professionalization_requires_the_full_approved_snapshot_contract(attribute, value):
    campaign = approved_campaign()
    setattr(campaign, attribute, value)

    with pytest.raises(HTTPException, match="Approve the campaign"):
        AIProfessionalizationService._assert_frozen_snapshot(campaign)


def test_professionalization_rejects_a_snapshot_with_an_unmatched_revision():
    snapshot = approved_snapshot()
    snapshot["approved_revision"] = 3

    with pytest.raises(HTTPException, match="Approve the campaign"):
        AIProfessionalizationService._assert_frozen_snapshot(approved_campaign(snapshot))


def test_provider_plan_is_bounded_and_rejects_css_or_duplicate_positions():
    with pytest.raises(ValidationError):
        AIProfessionalizationPlanEnvelope.model_validate(
            {"status": "ready", "header_style": "band", "css": "body { display: none; }"}
        )
    with pytest.raises(ValidationError, match="unique"):
        AIProfessionalizationPlanEnvelope.model_validate(
            {
                "status": "ready",
                "header_style": "band",
                "emphasis": [
                    {"position": 1, "treatment": "featured"},
                    {"position": 1, "treatment": "support"},
                ],
            }
        )


def test_render_payload_preserves_original_snapshot_and_item_order():
    snapshot = approved_snapshot()
    original = deepcopy(snapshot)
    plan = {
        "status": "ready",
        "header_style": "band",
        "emphasis": [{"position": 2, "treatment": "featured"}],
    }
    active_run = SimpleNamespace(
        is_active=True, snapshot_hash=frozen_snapshot_hash(snapshot), plan_json=plan
    )
    campaign = SimpleNamespace(snapshot_json=snapshot, professionalization_runs=[active_run])

    payload = build_campaign_render_payload(campaign, template=None)

    assert snapshot == original
    assert [item["name"] for item in payload["items"]] == ["First", "Second"]
    assert payload["professionalization_plan"] == plan


def test_stale_professionalization_overlay_falls_back_to_original_snapshot():
    snapshot = approved_snapshot()
    active_run = SimpleNamespace(
        is_active=True,
        snapshot_hash="0" * 64,
        plan_json={"status": "ready", "header_style": "band"},
    )
    campaign = SimpleNamespace(snapshot_json=snapshot, professionalization_runs=[active_run])

    assert "professionalization_plan" not in build_campaign_render_payload(campaign, template=None)
