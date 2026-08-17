"""Platform Admin endpoints for the central LeafletPilot WhatsApp channel.

Thin routing layer over the Evolution integration's operational state. Nothing
here may ever surface a secret: the Evolution API key, the webhook secret,
verification codes/code hashes and the full base URL are excluded by
construction — see `app/schemas/whatsapp.py` for the same guarantee on the
response models.

The `app.integrations.whatsapp.client` module is owned by a concurrently
developed piece of work; every reference to it is a lazy, in-function import
so this router can be wired up (and imported by tests/app startup) whether or
not that module has landed yet.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_platform_admin
from app.core.config import settings
from app.models import (
    Market,
    MarketUser,
    PlatformAdmin,
    PlatformAuditLog,
    User,
    UserWhatsAppIdentity,
    WhatsAppIntegrationState,
    WhatsAppSession,
    WhatsAppVerification,
)
from app.models.base import utc_now
from app.schemas.common import ListResponse
from app.schemas.whatsapp import (
    PlatformWhatsAppConnectionTestResponse,
    PlatformWhatsAppHealthRead,
    PlatformWhatsAppIdentityRead,
    PlatformWhatsAppMarketRead,
    WhatsAppRevokeRequest,
)
from app.services.phone import mask_phone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/integrations/whatsapp", tags=["platform"])


async def get_evolution_client() -> AsyncGenerator[Any, None]:
    """FastAPI dependency yielding an `EvolutionClientProtocol` client.

    Import is deliberately deferred to call time: `app.integrations.whatsapp
    .client` may not exist yet when this module is imported (see module
    docstring). Exposed so tests can `app.dependency_overrides[...]` it.
    """
    from app.integrations.whatsapp.client import build_evolution_client

    client = build_evolution_client()
    try:
        yield client
    finally:
        await client.aclose()


@router.get("/health", response_model=PlatformWhatsAppHealthRead)
async def whatsapp_health(
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> PlatformWhatsAppHealthRead:
    state: WhatsAppIntegrationState | None = None
    if settings.evolution_instance_name.strip():
        state = await session.scalar(
            select(WhatsAppIntegrationState).where(
                WhatsAppIntegrationState.instance_name == settings.evolution_instance_name
            )
        )

    configured = bool(
        settings.evolution_api_base_url.strip()
        and settings.evolution_api_key.strip()
        and settings.evolution_instance_name.strip()
        and settings.evolution_webhook_secret.strip()
        and settings.leafletpilot_whatsapp_number.strip()
    )

    base_url_host: str | None
    try:
        from app.integrations.whatsapp.client import evolution_base_url_host

        base_url_host = evolution_base_url_host()
    except ImportError:
        base_url_host = urlparse(settings.evolution_api_base_url).hostname

    verified_identity_count = await session.scalar(
        select(func.count())
        .select_from(UserWhatsAppIdentity)
        .where(UserWhatsAppIdentity.status == "verified")
    )
    pending_verification_count = await session.scalar(
        select(func.count())
        .select_from(WhatsAppVerification)
        .where(
            WhatsAppVerification.status == "pending",
            WhatsAppVerification.expires_at > utc_now(),
        )
    )
    market_count_with_verified_users = await session.scalar(
        select(func.count(func.distinct(MarketUser.market_id)))
        .select_from(MarketUser)
        .join(User, User.id == MarketUser.user_id)
        .join(UserWhatsAppIdentity, UserWhatsAppIdentity.user_id == User.id)
        .where(
            MarketUser.is_active.is_(True),
            UserWhatsAppIdentity.status == "verified",
        )
    )

    return PlatformWhatsAppHealthRead(
        enabled=settings.evolution_whatsapp_enabled,
        configured=configured,
        instance_name=settings.evolution_instance_name or None,
        official_number_masked=mask_phone(settings.leafletpilot_whatsapp_number) or None,
        base_url_host=base_url_host,
        connection_state=state.last_connection_state if state else None,
        connection_ok=state.last_connection_ok if state else None,
        last_connection_check_at=state.last_connection_check_at if state else None,
        last_connection_error=state.last_connection_error if state else None,
        last_webhook_at=state.last_webhook_at if state else None,
        last_webhook_event_type=state.last_webhook_event_type if state else None,
        last_inbound_message_at=state.last_inbound_message_at if state else None,
        last_outbound_at=state.last_outbound_at if state else None,
        last_outbound_error=state.last_outbound_error if state else None,
        last_outbound_error_at=state.last_outbound_error_at if state else None,
        verified_identity_count=verified_identity_count or 0,
        pending_verification_count=pending_verification_count or 0,
        market_count_with_verified_users=market_count_with_verified_users or 0,
    )


@router.post("/connection-test", response_model=PlatformWhatsAppConnectionTestResponse)
async def whatsapp_connection_test(
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
    client: Any = Depends(get_evolution_client),
) -> PlatformWhatsAppConnectionTestResponse:
    checked_at = utc_now()
    if not settings.evolution_whatsapp_enabled:
        return PlatformWhatsAppConnectionTestResponse(
            ok=False,
            state=None,
            detail="WhatsApp entegrasyonu devre dışı.",
            checked_at=checked_at,
        )

    from app.integrations.whatsapp.client import (
        EvolutionAuthError,
        EvolutionClientError,
        EvolutionUnavailableError,
    )

    ok = False
    state_value: str | None = None
    detail: str | None = None
    try:
        result = await client.fetch_connection_state()
        ok = result.ok
        state_value = result.state
        detail = None if ok else (result.detail or "Evolution API bağlantısı doğrulanamadı.")
    except EvolutionAuthError:
        logger.warning("Evolution connection test: authentication rejected.", exc_info=True)
        detail = "Evolution API kimlik doğrulaması reddedildi."
    except EvolutionUnavailableError:
        logger.warning("Evolution connection test: service unreachable.", exc_info=True)
        detail = "Evolution API'ye ulaşılamadı."
    except EvolutionClientError:
        logger.warning("Evolution connection test: unexpected client error.", exc_info=True)
        detail = "Evolution API beklenmeyen bir yanıt döndürdü."

    await _upsert_connection_state(session, checked_at=checked_at, ok=ok, state=state_value, detail=detail)
    _add_audit(
        session,
        admin,
        "EVOLUTION_CONNECTION_TESTED",
        "whatsapp_integration",
        None,
        {"instance": settings.evolution_instance_name, "ok": ok, "state": state_value},
    )
    await session.commit()
    return PlatformWhatsAppConnectionTestResponse(
        ok=ok,
        state=state_value,
        detail=detail,
        checked_at=checked_at,
    )


@router.get("/identities", response_model=ListResponse[PlatformWhatsAppIdentityRead])
async def list_whatsapp_identities(
    market_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = None,
    phone: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[PlatformWhatsAppIdentityRead]:
    conditions = []
    if status_filter:
        conditions.append(UserWhatsAppIdentity.status == status_filter)
    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append(or_(User.email.ilike(term), User.full_name.ilike(term)))
    if phone and phone.strip():
        digits = "".join(character for character in phone if character.isdigit())
        if digits:
            conditions.append(UserWhatsAppIdentity.phone_e164.ilike(f"%{digits}%"))
    if market_id is not None:
        member_exists = (
            select(MarketUser.id)
            .where(MarketUser.user_id == UserWhatsAppIdentity.user_id, MarketUser.market_id == market_id)
            .exists()
        )
        conditions.append(member_exists)

    count_statement = select(func.count()).select_from(UserWhatsAppIdentity).join(
        User, User.id == UserWhatsAppIdentity.user_id
    )
    statement = select(UserWhatsAppIdentity, User).join(User, User.id == UserWhatsAppIdentity.user_id)
    for condition in conditions:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    total = await session.scalar(count_statement)
    statement = (
        statement.order_by(
            UserWhatsAppIdentity.verified_at.desc().nullslast(),
            UserWhatsAppIdentity.created_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(statement)).all()
    identities = [identity for identity, _user in rows]
    users_by_id = {user.id: user for _identity, user in rows}

    markets_by_user_id: dict[UUID, list[PlatformWhatsAppMarketRead]] = {}
    user_ids = list(users_by_id.keys())
    if user_ids:
        membership_rows = (
            await session.execute(
                select(MarketUser, Market)
                .join(Market, Market.id == MarketUser.market_id)
                .where(MarketUser.user_id.in_(user_ids))
                .order_by(Market.name.asc())
            )
        ).all()
        for membership, market in membership_rows:
            markets_by_user_id.setdefault(membership.user_id, []).append(
                PlatformWhatsAppMarketRead(
                    market_id=market.id,
                    market_name=market.name,
                    market_slug=market.slug,
                    role=membership.role,
                    membership_active=membership.is_active,
                    market_active=market.is_active,
                    market_lifecycle_status=market.lifecycle_status,
                )
            )

    items = [
        PlatformWhatsAppIdentityRead(
            identity_id=identity.id,
            user_id=identity.user_id,
            user_email=users_by_id[identity.user_id].email,
            user_full_name=users_by_id[identity.user_id].full_name,
            user_is_active=users_by_id[identity.user_id].is_active,
            phone_e164=identity.phone_e164,
            phone_masked=mask_phone(identity.phone_e164),
            status=identity.status,
            verified_at=identity.verified_at,
            last_seen_at=identity.last_seen_at,
            revoked_at=identity.revoked_at,
            revoked_reason=identity.revoked_reason,
            markets=markets_by_user_id.get(identity.user_id, []),
        )
        for identity in identities
    ]
    return ListResponse(items=items, total=total or 0, limit=limit, offset=offset)


@router.post(
    "/identities/{identity_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_whatsapp_identity(
    identity_id: UUID,
    payload: WhatsAppRevokeRequest,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> None:
    identity = await session.get(UserWhatsAppIdentity, identity_id, with_for_update=True)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp kaydı bulunamadı.")
    if identity.status == "revoked":
        return

    now = utc_now()
    reason = payload.reason.strip() if payload.reason and payload.reason.strip() else None
    identity.status = "revoked"
    identity.revoked_at = now
    identity.revoked_reason = reason[:255] if reason else None
    identity.revoked_by_platform_admin_id = admin.id

    await session.execute(
        update(WhatsAppVerification)
        .where(
            WhatsAppVerification.user_id == identity.user_id,
            WhatsAppVerification.status == "pending",
        )
        .values(status="cancelled", consumed_at=now, failure_reason="revoked_by_platform_admin")
    )
    await session.execute(delete(WhatsAppSession).where(WhatsAppSession.user_id == identity.user_id))

    _add_audit(
        session,
        admin,
        "WHATSAPP_VERIFICATION_REVOKED",
        "user_whatsapp_identity",
        identity.id,
        {
            "user_id": str(identity.user_id),
            "phone_masked": mask_phone(identity.phone_e164),
            "reason": reason or "",
        },
    )
    await session.commit()


async def _upsert_connection_state(
    session: AsyncSession,
    *,
    checked_at: datetime,
    ok: bool,
    state: str | None,
    detail: str | None,
) -> None:
    instance_name = settings.evolution_instance_name
    values = {
        "last_connection_check_at": checked_at,
        "last_connection_state": state,
        "last_connection_ok": ok,
        "last_connection_error": detail,
        "updated_at": checked_at,
    }
    statement = (
        pg_insert(WhatsAppIntegrationState)
        .values(instance_name=instance_name, **values)
        .on_conflict_do_update(index_elements=["instance_name"], set_=values)
    )
    await session.execute(statement)


def _add_audit(
    session: AsyncSession,
    admin: PlatformAdmin | None,
    action: str,
    target_type: str,
    target_id: UUID | None,
    metadata: dict | None = None,
) -> None:
    session.add(
        PlatformAuditLog(
            actor_platform_admin_id=admin.id if admin else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_=metadata or {},
        )
    )
