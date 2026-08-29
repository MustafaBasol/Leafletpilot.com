from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.ai import AIProfessionalizationPlanEnvelope
from app.services.ai.professionalization import (
    AIProfessionalizationService,
    _is_accepted_source,
    frozen_snapshot_hash,
    immutable_brochure_facts,
    is_exportable_ai_run,
)
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


def image_run(snapshot, *, status="ready", active=False, source_run_id=None):
    return SimpleNamespace(
        id=source_run_id or "run-id",
        snapshot_hash=frozen_snapshot_hash(snapshot),
        status=status,
        is_active=active,
        generated_image_storage_key="markets/market/campaigns/campaign/professional.png",
        generated_image_file_id="file-id",
        validation_report_json={"accepted": True, "evidence_status": "verified"},
    )


def test_only_verified_ready_or_applied_runs_can_be_revision_sources():
    snapshot = approved_snapshot()
    ready = image_run(snapshot)
    failed = image_run(snapshot, status="failed")
    stale = image_run(snapshot)
    stale.snapshot_hash = "0" * 64

    assert _is_accepted_source(ready, frozen_snapshot_hash(snapshot)) is True
    assert _is_accepted_source(failed, frozen_snapshot_hash(snapshot)) is False
    assert _is_accepted_source(stale, frozen_snapshot_hash(snapshot)) is False


def test_failed_child_never_replaces_selected_successful_version():
    snapshot = approved_snapshot()
    active = image_run(snapshot, status="applied", active=True)
    failed_child = image_run(snapshot, status="failed")
    failed_child.is_active = False
    failed_child.validation_report_json = {
        "accepted": False,
        "evidence_status": "unverifiable",
    }

    assert is_exportable_ai_run(active, frozen_snapshot_hash(snapshot)) is True
    assert is_exportable_ai_run(failed_child, frozen_snapshot_hash(snapshot)) is False


def test_previous_ai_source_never_replaces_authoritative_commercial_facts():
    snapshot = approved_snapshot()
    snapshot["items"][0].update(old_price="2.49", currency="EUR", unit_label="1 L")

    facts = immutable_brochure_facts(snapshot)

    assert facts["products"][0] == {
        "name": "First",
        "price": "1.99",
        "old_price": "2.49",
        "currency": "EUR",
        "unit_label": "1 L",
        "quantity_label": None,
        "sort_order": 0,
    }


def test_transient_failures_have_bounded_separate_allowance(monkeypatch):
    monkeypatch.setattr(settings, "ai_professionalization_max_runs_per_campaign", 2)
    normal = SimpleNamespace(status="ready", failure_category=None)
    transient = SimpleNamespace(status="failed", failure_category="transient_provider")

    AIProfessionalizationService._assert_retry_quota([normal, transient, transient, transient])

    with pytest.raises(HTTPException) as normal_limit:
        AIProfessionalizationService._assert_retry_quota([normal, normal])
    assert normal_limit.value.detail["code"] == "professionalization_run_limit"

    with pytest.raises(HTTPException) as hard_limit:
        AIProfessionalizationService._assert_retry_quota(
            [normal, transient, transient, transient, transient]
        )
    assert hard_limit.value.detail["code"] == "professionalization_hard_limit"


class ScalarSession:
    def __init__(self, value):
        self.value = value

    async def scalar(self, _statement):
        return self.value


@pytest.mark.asyncio
async def test_cross_market_source_is_non_disclosing_not_found():
    with pytest.raises(HTTPException) as error:
        await AIProfessionalizationService._select_source_run(
            ScalarSession(None),
            campaign_id=uuid4(),
            market_id=uuid4(),
            snapshot_hash="a" * 64,
            instruction="Logoyu küçült",
            requested_source_run_id=uuid4(),
            history=[],
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_failed_or_cross_snapshot_source_cannot_be_revised():
    snapshot = approved_snapshot()
    failed = image_run(snapshot, status="failed")

    with pytest.raises(HTTPException) as failed_error:
        await AIProfessionalizationService._select_source_run(
            ScalarSession(failed),
            campaign_id=uuid4(),
            market_id=uuid4(),
            snapshot_hash=frozen_snapshot_hash(snapshot),
            instruction="Ürünleri büyüt",
            requested_source_run_id=uuid4(),
            history=[],
        )
    assert failed_error.value.detail["code"] == "invalid_professionalization_source"

    ready = image_run(snapshot)
    with pytest.raises(HTTPException) as stale_error:
        await AIProfessionalizationService._select_source_run(
            ScalarSession(ready),
            campaign_id=uuid4(),
            market_id=uuid4(),
            snapshot_hash="0" * 64,
            instruction="Ürünleri büyüt",
            requested_source_run_id=uuid4(),
            history=[],
        )
    assert stale_error.value.detail["code"] == "invalid_professionalization_source"


@pytest.mark.asyncio
async def test_plain_retry_of_failed_child_reuses_its_intended_ready_source():
    snapshot = approved_snapshot()
    source_id = uuid4()
    source = image_run(snapshot, status="ready", source_run_id=source_id)
    failed_child = SimpleNamespace(
        created_at=datetime.now(UTC),
        status="failed",
        source_type="previous_ai_output",
        source_run_id=source_id,
    )

    selected = await AIProfessionalizationService._select_source_run(
        ScalarSession(source),
        campaign_id=uuid4(),
        market_id=uuid4(),
        snapshot_hash=frozen_snapshot_hash(snapshot),
        instruction=None,
        requested_source_run_id=None,
        history=[failed_child],
    )

    assert selected is source
