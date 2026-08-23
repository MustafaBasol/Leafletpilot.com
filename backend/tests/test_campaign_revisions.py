from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import Campaign, CampaignItem, CampaignRevision
from app.schemas.revision import RevisionCommand, UndoRevisionRequest
from app.services import campaign as campaign_service
from app.services import revision as revision_service


class SessionDouble:
    def __init__(self, latest=None):
        self.added = []
        self.latest = latest
        self.commits = 0
        self.rollbacks = 0

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, value):
        return None

    async def scalar(self, statement):
        return self.latest


def make_campaign():
    market_id = uuid4()
    campaign = Campaign(
        id=uuid4(),
        market_id=market_id,
        title="Haftalık fırsatlar",
        status="preview_ready",
        currency="EUR",
        language="tr",
        draft_revision=0,
    )
    first = CampaignItem(
        id=uuid4(),
        campaign_id=campaign.id,
        market_id=market_id,
        raw_line="Sucuk 6.49",
        incoming_name="Sucuk",
        display_name="Sucuk",
        price=Decimal("6.49"),
        old_price=Decimal("7.49"),
        currency="EUR",
        sort_order=0,
        match_status="matched",
    )
    second = CampaignItem(
        id=uuid4(),
        campaign_id=campaign.id,
        market_id=market_id,
        raw_line="Kola 4.99",
        incoming_name="Kola",
        display_name="Kola",
        price=Decimal("4.99"),
        currency="EUR",
        sort_order=1,
        match_status="matched",
    )
    campaign.items = [first, second]
    return campaign, first, second


async def stub_locked_campaign(session, campaign_id, market_id):
    return session.campaign


async def no_existing_revision(session, campaign_id, market_id, request_id):
    return None


def test_revision_schema_is_discriminated_and_decimal_safe():
    command = RevisionCommand.model_validate(
        {
            "client_request_id": "panel-1",
            "source": "panel",
            "expected_revision": 0,
            "actions": [{"type": "update_price", "item_id": str(uuid4()), "price": "4.99"}],
        }
    )

    assert command.actions[0].price == Decimal("4.99")
    with pytest.raises(ValidationError):
        RevisionCommand.model_validate(
            {
                "client_request_id": "panel-2",
                "source": "panel",
                "expected_revision": 0,
                "actions": [{"type": "arbitrary_field_update", "item_id": str(uuid4())}],
            }
        )


@pytest.mark.asyncio
async def test_revision_applies_normalized_reorder_campaign_only_fields_and_audit(monkeypatch):
    campaign, first, second = make_campaign()
    session = SessionDouble()
    session.campaign = campaign
    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", no_existing_revision)

    result = await revision_service.apply_revision(
        session,
        campaign.id,
        RevisionCommand.model_validate(
            {
                "client_request_id": "panel-apply-1",
                "source": "panel",
                "expected_revision": 0,
                "actions": [
                    {"type": "move_item", "item_id": str(second.id), "target_position": 1},
                    {"type": "update_price", "item_id": str(first.id), "price": "5.25", "old_price": "6.49"},
                    {"type": "update_display_name", "item_id": str(first.id), "display_name": "Dana sucuk 400 g"},
                    {"type": "set_item_emphasis", "item_id": str(second.id), "emphasis": "hero"},
                    {"type": "remove_item", "item_id": str(first.id)},
                ],
            }
        ),
        campaign.market_id,
        actor_id=uuid4(),
    )

    assert result.revision.sequence == 1
    assert campaign.draft_revision == 1
    assert second.sort_order == 0
    assert first.sort_order == 1
    assert first.is_hidden is True
    assert first.display_name == "Dana sucuk 400 g"
    assert first.price == Decimal("5.25")
    assert second.is_hero is True
    assert campaign.product_count == 1
    assert any(isinstance(row, CampaignRevision) for row in session.added)
    assert session.commits == 1


@pytest.mark.asyncio
async def test_same_request_id_returns_existing_revision_without_second_mutation(monkeypatch):
    campaign, first, _ = make_campaign()
    campaign.draft_revision = 1
    existing = CampaignRevision(
        id=uuid4(), campaign_id=campaign.id, market_id=campaign.market_id, source="panel",
        request_id="panel-retry", sequence=1, status="applied", actions_json=[], before_snapshot_json={}, after_snapshot_json={}
    )
    session = SessionDouble()
    session.campaign = campaign

    async def existing_revision(*args):
        return existing

    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", existing_revision)
    result = await revision_service.apply_revision(
        session,
        campaign.id,
        RevisionCommand.model_validate(
            {"client_request_id": "panel-retry", "source": "panel", "expected_revision": 0, "actions": [{"type": "remove_item", "item_id": str(first.id)}]}
        ),
        campaign.market_id,
        actor_id=None,
    )

    assert result.idempotent is True
    assert not first.is_hidden
    assert session.commits == 0


@pytest.mark.asyncio
async def test_stale_revision_is_rejected_before_mutation(monkeypatch):
    campaign, first, _ = make_campaign()
    campaign.draft_revision = 3
    session = SessionDouble()
    session.campaign = campaign
    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", no_existing_revision)

    with pytest.raises(HTTPException) as exc:
        await revision_service.apply_revision(
            session,
            campaign.id,
            RevisionCommand.model_validate(
                {"client_request_id": "panel-stale", "source": "panel", "expected_revision": 2, "actions": [{"type": "remove_item", "item_id": str(first.id)}]}
            ),
            campaign.market_id,
            actor_id=None,
        )

    assert exc.value.status_code == 409
    assert not first.is_hidden


@pytest.mark.asyncio
async def test_undo_restores_previous_state_and_is_its_own_revision(monkeypatch):
    campaign, first, second = make_campaign()
    before = revision_service._draft_state(campaign)
    first.is_hidden = True
    second.sort_order = 0
    first.sort_order = 1
    campaign.draft_revision = 1
    latest = CampaignRevision(
        id=uuid4(), campaign_id=campaign.id, market_id=campaign.market_id, source="panel",
        request_id="panel-original", sequence=1, status="applied", actions_json=[], before_snapshot_json=before,
        after_snapshot_json=revision_service._draft_state(campaign),
    )
    session = SessionDouble(latest=latest)
    session.campaign = campaign
    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", no_existing_revision)

    result = await revision_service.undo_latest_revision(
        session,
        campaign.id,
        UndoRevisionRequest(client_request_id="panel-undo", expected_revision=1),
        campaign.market_id,
        actor_id=uuid4(),
    )

    assert result.revision.status == "undone"
    assert result.revision.reverts_revision_id == latest.id
    assert campaign.draft_revision == 2
    assert first.is_hidden is False
    assert [item.id for item in sorted(campaign.items, key=lambda item: item.sort_order)] == [first.id, second.id]


@pytest.mark.asyncio
async def test_approved_campaign_cannot_accept_post_approval_revision(monkeypatch):
    campaign, first, _ = make_campaign()
    campaign.status = "approved"
    session = SessionDouble()
    session.campaign = campaign
    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", no_existing_revision)

    with pytest.raises(HTTPException) as exc:
        await revision_service.apply_revision(
            session,
            campaign.id,
            RevisionCommand.model_validate(
                {"client_request_id": "panel-after-approval", "source": "panel", "expected_revision": 0, "actions": [{"type": "remove_item", "item_id": str(first.id)}]}
            ),
            campaign.market_id,
            actor_id=None,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_approval_freezes_the_current_revision_and_writes_audit_event(monkeypatch):
    campaign, first, _ = make_campaign()
    campaign.draft_revision = 4
    timestamp = datetime.now(UTC)
    campaign.product_count = 2
    campaign.matched_count = 2
    campaign.missing_count = 0
    campaign.low_confidence_count = 0
    campaign.created_at = timestamp
    campaign.updated_at = timestamp
    for item in campaign.items:
        item.is_hero = False
        item.is_hidden = False
        item.emphasis = "normal"
        item.created_at = timestamp
        item.updated_at = timestamp
    session = SessionDouble(latest=campaign.id)

    async def current_campaign(*args, **kwargs):
        return campaign

    async def default_template(*args, **kwargs):
        return SimpleNamespace(config_json={})

    async def persist(*args, **kwargs):
        return None

    def render_payload(candidate, template):
        return {
            "template_name": "Weekly",
            "items": [{"name": candidate.items[0].display_name, "price": "6.49"}],
        }

    from app.services import campaign_rendering

    monkeypatch.setattr(campaign_service, "get_campaign", current_campaign)
    monkeypatch.setattr(campaign_service, "_get_default_template", default_template)
    monkeypatch.setattr(campaign_service, "_persist", persist)
    monkeypatch.setattr(campaign_rendering, "build_campaign_render_payload", render_payload)

    response = await campaign_service.finalize_campaign(
        session, campaign.id, campaign.market_id, actor_id=uuid4()
    )

    assert campaign.status == "approved"
    assert campaign.approved_revision == 4
    assert response.snapshot["approved_revision"] == 4
    assert response.snapshot["items"][0]["name"] == "Sucuk"
    assert any(getattr(row, "action", None) == "campaign_draft_approved" for row in session.added)

    first.display_name = "Catalog-side rename after approval"
    assert response.snapshot["items"][0]["name"] == "Sucuk"
