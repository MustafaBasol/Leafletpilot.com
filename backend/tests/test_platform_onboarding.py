from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.deps import get_current_platform_admin, require_market_member
from app.api.routes.platform import _invitation_summary
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
    assert summary["delivery_status"] == "manual"
    assert summary["is_effective"] is True
    assert "token_hash" not in summary
