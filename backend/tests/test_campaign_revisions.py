from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import Campaign, CampaignItem, CampaignRevision
from app.schemas.revision import (
    CampaignApprovalRequest,
    PanelRevisionCommand,
    PanelUndoRevisionRequest,
    RevisionCommand,
    UndoRevisionRequest,
)
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
        request_id="panel-retry",
        request_fingerprint=campaign_service.canonical_request_fingerprint(
            source="panel",
            expected_revision=0,
            actions=[{"type": "remove_item", "item_id": str(first.id)}],
        ),
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
        session, campaign.id, campaign.market_id, expected_revision=4, actor_id=uuid4()
    )

    assert campaign.status == "approved"
    assert campaign.approved_revision == 4
    assert response.snapshot["approved_revision"] == 4
    assert response.snapshot["items"][0]["name"] == "Sucuk"
    assert any(getattr(row, "action", None) == "campaign_draft_approved" for row in session.added)

    first.display_name = "Catalog-side rename after approval"
    assert response.snapshot["items"][0]["name"] == "Sucuk"


def test_panel_request_schemas_forbid_spoofed_sources_and_trust_panel_origin():
    with pytest.raises(ValidationError):
        PanelRevisionCommand.model_validate(
            {
                "client_request_id": "panel-spoof",
                "source": "ai",
                "expected_revision": 0,
                "actions": [{"type": "remove_item", "item_id": str(uuid4())}],
            }
        )
    with pytest.raises(ValidationError):
        PanelUndoRevisionRequest.model_validate(
            {"client_request_id": "panel-undo-spoof", "source": "system", "expected_revision": 0}
        )

    command = PanelRevisionCommand.model_validate(
        {
            "client_request_id": "panel-trusted",
            "expected_revision": 0,
            "actions": [{"type": "remove_item", "item_id": str(uuid4())}],
        }
    ).trusted_command()
    undo = PanelUndoRevisionRequest(
        client_request_id="panel-undo-trusted", expected_revision=0
    ).trusted_request()

    assert command.source == "panel"
    assert undo.source == "panel"
    assert CampaignApprovalRequest(expected_revision=0).expected_revision == 0


@pytest.mark.asyncio
async def test_same_request_id_with_different_actions_is_rejected(monkeypatch):
    campaign, first, _ = make_campaign()
    campaign.draft_revision = 1
    existing = CampaignRevision(
        id=uuid4(),
        campaign_id=campaign.id,
        market_id=campaign.market_id,
        source="panel",
        request_id="panel-conflict",
        request_fingerprint=campaign_service.canonical_request_fingerprint(
            source="panel",
            expected_revision=0,
            actions=[{"type": "remove_item", "item_id": str(first.id)}],
        ),
        sequence=1,
        status="applied",
        actions_json=[],
        before_snapshot_json={},
        after_snapshot_json={},
    )
    session = SessionDouble()
    session.campaign = campaign

    async def existing_revision(*args):
        return existing

    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", existing_revision)

    with pytest.raises(HTTPException) as exc:
        await revision_service.apply_revision(
            session,
            campaign.id,
            RevisionCommand.model_validate(
                {
                    "client_request_id": "panel-conflict",
                    "source": "panel",
                    "expected_revision": 0,
                    "actions": [
                        {
                            "type": "update_price",
                            "item_id": str(first.id),
                            "price": "5.99",
                        }
                    ],
                }
            ),
            campaign.market_id,
            actor_id=None,
        )

    assert exc.value.status_code == 409
    assert first.price == Decimal("6.49")


@pytest.mark.asyncio
async def test_same_request_id_with_different_expected_revision_is_rejected(monkeypatch):
    campaign, first, _ = make_campaign()
    campaign.draft_revision = 1
    existing = CampaignRevision(
        id=uuid4(),
        campaign_id=campaign.id,
        market_id=campaign.market_id,
        source="panel",
        request_id="panel-expected-conflict",
        request_fingerprint=campaign_service.canonical_request_fingerprint(
            source="panel",
            expected_revision=0,
            actions=[{"type": "remove_item", "item_id": str(first.id)}],
        ),
        sequence=1,
        status="applied",
        actions_json=[],
        before_snapshot_json={},
        after_snapshot_json={},
    )
    session = SessionDouble()
    session.campaign = campaign

    async def existing_revision(*args):
        return existing

    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", existing_revision)

    with pytest.raises(HTTPException) as exc:
        await revision_service.apply_revision(
            session,
            campaign.id,
            RevisionCommand.model_validate(
                {
                    "client_request_id": "panel-expected-conflict",
                    "source": "panel",
                    "expected_revision": 1,
                    "actions": [{"type": "remove_item", "item_id": str(first.id)}],
                }
            ),
            campaign.market_id,
            actor_id=None,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_undo_request_id_mismatch_is_rejected(monkeypatch):
    campaign, _, _ = make_campaign()
    campaign.draft_revision = 1
    existing = CampaignRevision(
        id=uuid4(),
        campaign_id=campaign.id,
        market_id=campaign.market_id,
        source="panel",
        request_id="panel-undo-conflict",
        request_fingerprint=campaign_service.canonical_request_fingerprint(
            source="panel", expected_revision=1, actions=[{"type": "undo"}]
        ),
        sequence=1,
        status="undone",
        actions_json=[],
        before_snapshot_json={},
        after_snapshot_json={},
    )
    session = SessionDouble()
    session.campaign = campaign

    async def existing_revision(*args):
        return existing

    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", existing_revision)

    with pytest.raises(HTTPException) as exc:
        await revision_service.undo_latest_revision(
            session,
            campaign.id,
            UndoRevisionRequest(client_request_id="panel-undo-conflict", expected_revision=0),
            campaign.market_id,
            actor_id=None,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_second_immediate_undo_is_rejected_without_implicit_redo(monkeypatch):
    campaign, first, _ = make_campaign()
    campaign.draft_revision = 2
    latest = CampaignRevision(
        id=uuid4(),
        campaign_id=campaign.id,
        market_id=campaign.market_id,
        source="panel",
        request_id="panel-prior-undo",
        request_fingerprint="f" * 64,
        sequence=2,
        status="undone",
        actions_json=[],
        before_snapshot_json={},
        after_snapshot_json={},
    )
    session = SessionDouble(latest=latest)
    session.campaign = campaign
    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", no_existing_revision)

    with pytest.raises(HTTPException) as exc:
        await revision_service.undo_latest_revision(
            session,
            campaign.id,
            UndoRevisionRequest(client_request_id="panel-second-undo", expected_revision=2),
            campaign.market_id,
            actor_id=None,
        )

    assert exc.value.status_code == 409
    assert first.is_hidden is None
    assert campaign.draft_revision == 2


@pytest.mark.asyncio
async def test_approval_rejects_stale_expected_revision_without_mutation(monkeypatch):
    campaign, _, _ = make_campaign()
    campaign.draft_revision = 4
    session = SessionDouble(latest=campaign.id)

    async def current_campaign(*args, **kwargs):
        return campaign

    monkeypatch.setattr(campaign_service, "get_campaign", current_campaign)

    with pytest.raises(HTTPException) as exc:
        await campaign_service.finalize_campaign(
            session,
            campaign.id,
            campaign.market_id,
            expected_revision=3,
            actor_id=uuid4(),
        )

    assert exc.value.status_code == 409
    assert campaign.frozen_at is None
    assert campaign.snapshot_json is None
    assert campaign.approved_revision is None


@pytest.mark.asyncio
async def test_approval_keeps_campaign_presentation_values_when_catalog_changes(monkeypatch):
    campaign, first, _ = make_campaign()
    campaign.draft_revision = 4
    campaign.product_count = 2
    campaign.matched_count = 2
    campaign.missing_count = 0
    campaign.low_confidence_count = 0
    timestamp = datetime.now(UTC)
    campaign.created_at = timestamp
    campaign.updated_at = timestamp
    first.market_product_id = uuid4()
    first.display_name = "Campaign-only sucuk"
    first.price = Decimal("5.25")
    first.old_price = Decimal("6.49")
    first.emphasis = "large"
    first.image_override_product_image_id = uuid4()
    for item in campaign.items:
        item.created_at = timestamp
        item.updated_at = timestamp
        item.is_hero = False
        item.is_hidden = False
        item.emphasis = "normal"
    first.emphasis = "large"
    session = SessionDouble(latest=campaign.id)

    async def current_campaign(*args, **kwargs):
        return campaign

    async def default_template(*args, **kwargs):
        return SimpleNamespace(config_json={})

    async def changed_catalog(*args, **kwargs):
        return SimpleNamespace(product=SimpleNamespace(name="Catalog rename"))

    async def persist(*args, **kwargs):
        return None

    def render_payload(candidate, template):
        item = candidate.items[0]
        return {
            "items": [
                {
                    "name": item.display_name,
                    "price": str(item.price),
                    "old_price": str(item.old_price),
                    "emphasis": item.emphasis,
                    "image_override_product_image_id": str(item.image_override_product_image_id),
                }
            ]
        }

    from app.services import campaign_rendering
    from app.services.campaign_rendering import build_campaign_render_payload

    monkeypatch.setattr(campaign_service, "get_campaign", current_campaign)
    monkeypatch.setattr(campaign_service, "_get_default_template", default_template)
    monkeypatch.setattr(campaign_service, "validate_visible_market_product", changed_catalog)
    monkeypatch.setattr(campaign_service, "_persist", persist)
    monkeypatch.setattr(campaign_rendering, "build_campaign_render_payload", render_payload)

    response = await campaign_service.finalize_campaign(
        session,
        campaign.id,
        campaign.market_id,
        expected_revision=4,
        actor_id=uuid4(),
    )

    assert response.snapshot["items"][0] == {
        "name": "Campaign-only sucuk",
        "price": "5.25",
        "old_price": "6.49",
        "emphasis": "large",
        "image_override_product_image_id": str(first.image_override_product_image_id),
    }
    first.display_name = "Live catalog rename"
    first.price = Decimal("99.99")
    first.emphasis = "normal"
    assert build_campaign_render_payload(campaign, None)["items"][0]["name"] == "Campaign-only sucuk"


@pytest.mark.asyncio
async def test_retained_legacy_render_mutations_advance_the_shared_draft_version(monkeypatch):
    from app.schemas.campaign import (
        CampaignItemCreate,
        CampaignItemResolveMatch,
        CampaignItemUpdate,
        CampaignUpdate,
    )

    active = {}

    async def current_campaign(*args, **kwargs):
        return active["campaign"]

    async def persist(*args, **kwargs):
        return None

    monkeypatch.setattr(campaign_service, "get_campaign", current_campaign)
    monkeypatch.setattr(campaign_service, "_persist", persist)

    async def assert_invalidated(operation):
        campaign, first, second = make_campaign()
        active["campaign"] = campaign
        session = SessionDouble()
        await operation(session, campaign, first, second)
        assert campaign.draft_revision == 1
        assert any(isinstance(row, CampaignRevision) for row in session.added)
        with pytest.raises(HTTPException) as exc:
            revision_service._assert_expected_revision(campaign, 0)
        assert exc.value.status_code == 409

    await assert_invalidated(
        lambda session, campaign, first, second: campaign_service.update_campaign(
            session, campaign.id, CampaignUpdate(title="Updated"), campaign.market_id
        )
    )
    await assert_invalidated(
        lambda session, campaign, first, second: campaign_service.add_campaign_item(
            session,
            campaign.id,
            CampaignItemCreate(raw_line="Milk 1.99", incoming_name="Milk"),
            campaign.market_id,
        )
    )
    await assert_invalidated(
        lambda session, campaign, first, second: campaign_service.update_campaign_item(
            session,
            campaign.id,
            first.id,
            CampaignItemUpdate(display_name="Campaign item"),
            campaign.market_id,
        )
    )
    await assert_invalidated(
        lambda session, campaign, first, second: campaign_service.reorder_campaign_items(
            session, campaign.id, [second.id, first.id], campaign.market_id
        )
    )
    await assert_invalidated(
        lambda session, campaign, first, second: campaign_service.resolve_campaign_item_match(
            session,
            campaign.id,
            first.id,
            CampaignItemResolveMatch(resolution="new_product_needed"),
            campaign.market_id,
        )
    )


@pytest.mark.asyncio
async def test_hidden_items_do_not_change_structured_visible_reorder_positions(monkeypatch):
    campaign, first, second = make_campaign()
    hidden = CampaignItem(
        id=uuid4(),
        campaign_id=campaign.id,
        market_id=campaign.market_id,
        raw_line="Hidden",
        incoming_name="Hidden",
        display_name="Hidden",
        price=Decimal("1.00"),
        currency="EUR",
        sort_order=1,
        match_status="matched",
        is_hidden=True,
    )
    second.sort_order = 2
    campaign.items = [first, hidden, second]
    session = SessionDouble()
    session.campaign = campaign
    monkeypatch.setattr(revision_service, "_get_locked_campaign", stub_locked_campaign)
    monkeypatch.setattr(revision_service, "_find_by_request_id", no_existing_revision)

    await revision_service.apply_revision(
        session,
        campaign.id,
        RevisionCommand.model_validate(
            {
                "client_request_id": "panel-visible-move",
                "source": "panel",
                "expected_revision": 0,
                "actions": [{"type": "move_item", "item_id": str(second.id), "target_position": 1}],
            }
        ),
        campaign.market_id,
        actor_id=None,
    )

    visible = [item.id for item in sorted(campaign.items, key=lambda item: item.sort_order) if not item.is_hidden]
    assert visible == [second.id, first.id]

def test_approval_and_legacy_finalize_routes_share_the_versioned_request_contract():

    import inspect

    from app.api.routes.campaigns import approve_campaign, finalize_campaign

    for endpoint in (approve_campaign, finalize_campaign):
        payload = inspect.signature(endpoint).parameters["payload"]
        assert payload.annotation is CampaignApprovalRequest
    assert "expected_revision" in CampaignApprovalRequest.model_fields
