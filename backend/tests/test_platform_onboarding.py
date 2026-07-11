from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.deps import get_current_market_membership, get_current_platform_admin, require_market_member
from app.api.routes.platform import _invitation_summary, list_platform_markets, platform_overview
from app.core.lifecycle import market_allows_mutations
from app.core.security import create_access_token, create_platform_access_token, hash_password, hash_signup_throttle_key, verify_password
from app.models import Market, MarketInvitation, MarketUser, PlatformAdmin, PlatformAuditLog, User
from app.models.base import utc_now


def test_platform_admin_password_is_hashed() -> None:
    password_hash = hash_password("StrongPassword123!")
    assert "StrongPassword123!" not in password_hash
    assert verify_password("StrongPassword123!", password_hash)


def test_signup_throttle_key_is_hashed() -> None:
    key = hash_signup_throttle_key("127.0.0.1:person@example.com")
    assert "127.0.0.1" not in key
    assert "person@example.com" not in key
    assert len(key) == 64


def test_market_allows_mutations_handles_none_and_lifecycle_states() -> None:
    assert market_allows_mutations(None) is False
    assert market_allows_mutations(Market(name="Active", slug="active", lifecycle_status="active", is_active=True)) is True
    assert market_allows_mutations(Market(name="Trial", slug="trial", lifecycle_status="trial", is_active=True)) is True
    assert market_allows_mutations(Market(name="Suspended", slug="suspended", lifecycle_status="suspended", is_active=True)) is False
    assert market_allows_mutations(Market(name="Archived", slug="archived", lifecycle_status="archived", is_active=False)) is False
    assert market_allows_mutations(Market(name="Inactive", slug="inactive", lifecycle_status="active", is_active=False)) is False


@pytest.mark.asyncio
async def test_platform_dependency_rejects_tenant_jwt() -> None:
    class Session:
        async def scalar(self, statement):
            return None

    token = create_access_token(str(uuid4()))
    credentials = type("Credentials", (), {"scheme": "Bearer", "credentials": token})()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_platform_admin(credentials=credentials, session=Session())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_tenant_dependency_rejects_platform_jwt() -> None:
    from app.api.deps import get_current_user

    token = create_platform_access_token(str(uuid4()))
    credentials = type("Credentials", (), {"scheme": "Bearer", "credentials": token})()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=credentials, session=object())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_suspended_market_fails_closed_for_member_dependency() -> None:
    market_id = uuid4()
    user_id = uuid4()
    user = User(id=user_id, email=f"member-{user_id}@example.com", is_active=True)
    market = Market(
        id=market_id,
        name="Suspended Market",
        slug=f"suspended-{market_id}",
        is_active=True,
        lifecycle_status="suspended",
    )
    membership = MarketUser(market_id=market_id, user_id=user_id, role="market_admin", is_active=True)
    membership.market = market

    class Session:
        async def scalar(self, statement):
            return membership

    with pytest.raises(HTTPException) as exc_info:
        await require_market_member(x_market_id=market_id, current_user=user, session=Session())
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_archived_market_returns_archived_specific_member_dependency_error() -> None:
    market_id = uuid4()
    user_id = uuid4()
    user = User(id=user_id, email=f"member-{user_id}@example.com", is_active=True)
    market = Market(
        id=market_id,
        name="Archived Market",
        slug=f"archived-{market_id}",
        is_active=False,
        lifecycle_status="archived",
    )
    membership = MarketUser(market_id=market_id, user_id=user_id, role="market_admin", is_active=True)
    membership.market = market

    class Session:
        async def scalar(self, statement):
            return membership

    with pytest.raises(HTTPException) as exc_info:
        await get_current_market_membership(x_market_id=market_id, current_user=user, session=Session())
    assert exc_info.value.status_code == 403
    assert "arşiv" in exc_info.value.detail


@pytest.mark.asyncio
async def test_list_platform_markets_uses_database_page_and_preserves_total() -> None:
    market_ids = [uuid4(), uuid4()]
    now = utc_now()
    page_markets = [
        Market(
            id=market_ids[0],
            name="Page Market 1",
            slug="page-1",
            lifecycle_status="active",
            onboarding_status="completed",
            created_at=now,
        ),
        Market(
            id=market_ids[1],
            name="Page Market 2",
            slug="page-2",
            lifecycle_status="active",
            onboarding_status="not_started",
            created_at=now,
        ),
    ]

    class Result:
        def all(self):
            return [
                (page_markets[0], None, 3, 1, 2, 4),
                (page_markets[1], None, 1, 1, 0, 0),
            ]

    class Session:
        def __init__(self):
            self.scalar_statement = None
            self.execute_statement = None

        async def scalar(self, statement):
            self.scalar_statement = statement
            return 5

        async def execute(self, statement):
            self.execute_statement = statement
            return Result()

    session = Session()
    response = await list_platform_markets(limit=2, offset=2, session=session)

    assert response.total == 5
    assert response.limit == 2
    assert response.offset == 2
    assert [item.id for item in response.items] == market_ids
    assert [item.member_count for item in response.items] == [3, 1]
    assert [item.readiness.state for item in response.items] == ["ready", "onboarding"]
    assert session.execute_statement._limit_clause is not None
    assert session.execute_statement._offset_clause is not None


@pytest.mark.asyncio
async def test_platform_overview_uses_aggregate_readiness_counts() -> None:
    class ExecuteResult:
        def all(self):
            return [
                ("awaiting_owner", 2),
                ("onboarding", 3),
                ("ready", 4),
                ("suspended", 1),
            ]

    class ScalarResult:
        def all(self):
            return []

    class Session:
        async def scalar(self, statement):
            return 7

        async def execute(self, statement):
            return ExecuteResult()

        async def scalars(self, statement):
            return ScalarResult()

    overview = await platform_overview(session=Session())

    assert overview.pending_signup_count == 7
    assert overview.markets_awaiting_owner == 2
    assert overview.markets_onboarding == 3
    assert overview.ready_markets == 4
    assert overview.suspended_markets == 1


def test_platform_admin_model_is_not_market_membership() -> None:
    admin = PlatformAdmin(email="admin@example.com", full_name="Admin", password_hash="hashed")
    assert not isinstance(admin, MarketUser)


def test_platform_audit_log_does_not_require_tenant_user_actor() -> None:
    admin_id = uuid4()
    audit = PlatformAuditLog(
        actor_platform_admin_id=admin_id,
        action="owner_invitation_created",
        target_type="market_invitation",
        target_id=uuid4(),
        metadata_={"delivery_status": "manual"},
    )

    assert audit.actor_platform_admin_id == admin_id
    assert "token" not in audit.metadata_


def test_platform_invitation_summary_never_exposes_token_hash() -> None:
    now = utc_now()
    invitation = MarketInvitation(
        id=uuid4(),
        market_id=uuid4(),
        email="owner@example.com",
        role="market_admin",
        token_hash="hashed-token",
        status="pending",
        expires_at=now.replace(year=now.year + 1),
        created_at=now,
    )

    summary = _invitation_summary(invitation).model_dump()
    assert summary["delivery_status"] == "pending"
    assert summary["is_effective"] is True
    assert "token_hash" not in summary
