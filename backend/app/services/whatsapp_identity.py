"""Domain logic for the central LeafletPilot WhatsApp channel's identity flows.

Everything a market member sees or triggers about their own (or a teammate's)
WhatsApp verification lives here: the per-member status roll-up, requesting a
verification code, polling it, cancelling it, and revoking a verified
identity. Routes in `app/api/routes/whatsapp.py` stay thin wrappers around
this module — see that file for auth wiring.

Security invariants enforced throughout this module:
    * Every membership lookup filters on `id == membership_id AND
      market_id == market_id` — a membership id from another market must
      never be distinguishable from one that doesn't exist at all (both raise
      the same 404).
    * A verification's plaintext code is only ever returned once, by
      `request_verification`, to the caller that just created it. Nothing in
      this module logs it, audits it, or re-derives it from the hash.
    * Phone numbers written to `ActivityLog.metadata_` are always masked via
      `mask_phone` — never the raw E.164 value.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import (
    generate_whatsapp_verification_code,
    hash_whatsapp_verification_code,
)
from app.models import (
    ActivityLog,
    Market,
    MarketUser,
    User,
    UserWhatsAppIdentity,
    WhatsAppSession,
    WhatsAppVerification,
)
from app.models.base import utc_now
from app.schemas.whatsapp import WhatsAppMemberStatusRead, WhatsAppVerificationRead
from app.services.phone import mask_phone, normalize_phone_e164
from app.services.rate_limit import WHATSAPP_USER_KEY, consume_rate_limit


async def list_market_whatsapp_status(
    session: AsyncSession,
    market_id: UUID,
    *,
    current_user_id: UUID,
    can_manage: bool,
) -> list[WhatsAppMemberStatusRead]:
    memberships = (
        await session.scalars(
            select(MarketUser)
            .options(selectinload(MarketUser.user))
            .where(MarketUser.market_id == market_id)
        )
    ).unique().all()
    if not memberships:
        return []

    user_ids = [membership.user_id for membership in memberships]

    verified_identities = (
        await session.scalars(
            select(UserWhatsAppIdentity).where(
                UserWhatsAppIdentity.user_id.in_(user_ids),
                UserWhatsAppIdentity.status == "verified",
            )
        )
    ).all()
    verified_by_user = {identity.user_id: identity for identity in verified_identities}

    revoked_identities = (
        await session.scalars(
            select(UserWhatsAppIdentity)
            .where(
                UserWhatsAppIdentity.user_id.in_(user_ids),
                UserWhatsAppIdentity.status == "revoked",
            )
            .order_by(UserWhatsAppIdentity.revoked_at.desc())
        )
    ).all()
    latest_revoked_by_user: dict[UUID, UserWhatsAppIdentity] = {}
    for identity in revoked_identities:
        latest_revoked_by_user.setdefault(identity.user_id, identity)

    verifications = (
        await session.scalars(
            select(WhatsAppVerification)
            .where(WhatsAppVerification.user_id.in_(user_ids))
            .order_by(WhatsAppVerification.created_at.desc())
        )
    ).all()
    latest_verification_by_user: dict[UUID, WhatsAppVerification] = {}
    for verification in verifications:
        latest_verification_by_user.setdefault(verification.user_id, verification)

    now = utc_now()
    rows: list[WhatsAppMemberStatusRead] = []
    for membership in memberships:
        user: User = membership.user
        verified_identity = verified_by_user.get(membership.user_id)
        latest_verification = latest_verification_by_user.get(membership.user_id)

        pending_verification: WhatsAppVerification | None = None
        if (
            latest_verification is not None
            and latest_verification.status == "pending"
            and latest_verification.expires_at > now
        ):
            pending_verification = latest_verification

        is_expired = latest_verification is not None and (
            latest_verification.status == "expired"
            or (latest_verification.status == "pending" and latest_verification.expires_at <= now)
        )

        if verified_identity is not None:
            derived_status = "verified"
        elif pending_verification is not None:
            derived_status = "pending"
        elif is_expired:
            derived_status = "expired"
        elif latest_revoked_by_user.get(membership.user_id) is not None:
            derived_status = "revoked"
        else:
            derived_status = "not_configured"

        row_can_manage = can_manage or membership.user_id == current_user_id

        verified_phone: str | None = None
        verified_phone_masked: str | None = None
        verified_at = None
        last_seen_at = None
        if derived_status == "verified" and verified_identity is not None:
            verified_phone_masked = mask_phone(verified_identity.phone_e164)
            if row_can_manage:
                verified_phone = verified_identity.phone_e164
            verified_at = verified_identity.verified_at
            last_seen_at = verified_identity.last_seen_at

        revoked_at = None
        revoked_identity = latest_revoked_by_user.get(membership.user_id)
        if derived_status == "revoked" and revoked_identity is not None:
            revoked_at = revoked_identity.revoked_at

        rows.append(
            WhatsAppMemberStatusRead(
                membership_id=membership.id,
                user_id=membership.user_id,
                email=user.email,
                full_name=user.full_name,
                role=membership.role,
                is_active=membership.is_active,
                status=derived_status,
                verified_phone=verified_phone,
                verified_phone_masked=verified_phone_masked,
                verified_at=verified_at,
                last_seen_at=last_seen_at,
                revoked_at=revoked_at,
                pending_verification_id=pending_verification.id if pending_verification else None,
                pending_expires_at=pending_verification.expires_at if pending_verification else None,
                claimed_phone=(
                    latest_verification.claimed_phone_e164
                    if pending_verification is not None and latest_verification is not None
                    else None
                ),
                can_manage=row_can_manage,
            )
        )

    status_rank = {"verified": 0, "pending": 1}
    rows.sort(key=lambda row: (status_rank.get(row.status, 2), row.email.lower()))
    return rows


async def request_verification(
    session: AsyncSession,
    *,
    market_id: UUID,
    membership_id: UUID,
    actor_user_id: UUID,
    actor_is_market_admin: bool,
    claimed_phone: str | None,
    market_country_code: str | None,
) -> tuple[WhatsAppVerification, str]:
    if not settings.evolution_whatsapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WhatsApp kanalı şu anda etkin değil.",
        )

    membership = await session.scalar(
        select(MarketUser)
        .options(selectinload(MarketUser.user))
        .where(MarketUser.id == membership_id, MarketUser.market_id == market_id)
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Üye bulunamadı.")
    if not membership.is_active or not membership.user.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu kullanıcı pasif durumda.")

    if not (actor_is_market_admin or membership.user_id == actor_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yetkiniz bulunmuyor.",
        )

    target_user_id = membership.user_id

    already_verified = await session.scalar(
        select(UserWhatsAppIdentity).where(
            UserWhatsAppIdentity.user_id == target_user_id,
            UserWhatsAppIdentity.status == "verified",
        )
    )
    if already_verified is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kullanıcının WhatsApp numarası zaten doğrulanmış. Önce mevcut doğrulamayı kaldırın.",
        )

    over_limit = await consume_rate_limit(
        session,
        key_type=WHATSAPP_USER_KEY,
        raw_value=str(target_user_id),
        limit=settings.whatsapp_verification_request_limit,
    )
    if over_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Çok fazla doğrulama isteği gönderildi. Lütfen biraz sonra tekrar deneyin.",
        )

    latest_pending = await session.scalar(
        select(WhatsAppVerification)
        .where(WhatsAppVerification.user_id == target_user_id, WhatsAppVerification.status == "pending")
        .order_by(WhatsAppVerification.created_at.desc())
    )
    if latest_pending is not None:
        cooldown = timedelta(seconds=settings.whatsapp_verification_resend_cooldown_seconds)
        if utc_now() - latest_pending.created_at < cooldown:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Yeni kod istemek için biraz beklemeniz gerekiyor.",
            )

    # Row-lock every currently-pending verification for this user before superseding them, so
    # two concurrent requests cannot both leave a pending row alive (the partial unique index
    # `uq_whatsapp_verifications_pending_user` is the backstop below).
    pending_rows = (
        await session.scalars(
            select(WhatsAppVerification)
            .where(WhatsAppVerification.user_id == target_user_id, WhatsAppVerification.status == "pending")
            .with_for_update()
        )
    ).all()
    now = utc_now()
    for pending_row in pending_rows:
        pending_row.status = "cancelled"
        pending_row.consumed_at = now
        pending_row.failure_reason = "superseded"

    normalized_claimed_phone: str | None = None
    if claimed_phone and claimed_phone.strip():
        normalized_claimed_phone = normalize_phone_e164(claimed_phone, default_region=market_country_code)
        if normalized_claimed_phone is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Telefon numarası geçersiz. Lütfen ülke koduyla birlikte girin.",
            )

    code = generate_whatsapp_verification_code()
    verification = WhatsAppVerification(
        user_id=target_user_id,
        market_id=market_id,
        membership_id=membership_id,
        requested_by_user_id=actor_user_id,
        code_hash=hash_whatsapp_verification_code(code),
        claimed_phone_e164=normalized_claimed_phone,
        status="pending",
        expires_at=now + timedelta(minutes=settings.whatsapp_verification_expire_minutes),
        attempt_count=0,
    )
    session.add(verification)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aynı anda başka bir doğrulama isteği işlendi. Lütfen tekrar deneyin.",
        ) from exc

    session.add(
        ActivityLog(
            market_id=market_id,
            user_id=actor_user_id,
            entity_type="whatsapp_verification",
            entity_id=verification.id,
            action="WHATSAPP_VERIFICATION_REQUESTED",
            description="WhatsApp verification requested",
            metadata_={
                "target_user_id": str(target_user_id),
                "claimed_phone_masked": mask_phone(normalized_claimed_phone),
            },
        )
    )

    return verification, code


async def get_verification(
    session: AsyncSession,
    verification_id: UUID,
    *,
    market_id: UUID,
    actor_user_id: UUID,
    actor_is_market_admin: bool,
) -> WhatsAppVerificationRead:
    verification = await session.scalar(
        select(WhatsAppVerification).where(
            WhatsAppVerification.id == verification_id,
            WhatsAppVerification.market_id == market_id,
        )
    )
    if verification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doğrulama kaydı bulunamadı.")
    if not (actor_is_market_admin or verification.user_id == actor_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yetkiniz bulunmuyor.",
        )

    reported_status = verification.status
    verified_phone: str | None = None
    verified_phone_masked: str | None = None

    if reported_status == "pending" and verification.expires_at <= utc_now():
        reported_status = "expired"

    verified_identity = await session.scalar(
        select(UserWhatsAppIdentity).where(
            UserWhatsAppIdentity.user_id == verification.user_id,
            UserWhatsAppIdentity.status == "verified",
        )
    )
    if verified_identity is not None and verified_identity.verified_at >= verification.created_at:
        reported_status = "verified"
        verified_phone_masked = mask_phone(verified_identity.phone_e164)
        if actor_is_market_admin or verification.user_id == actor_user_id:
            verified_phone = verified_identity.phone_e164

    return WhatsAppVerificationRead(
        verification_id=verification.id,
        membership_id=verification.membership_id,
        user_id=verification.user_id,
        status=reported_status,
        expires_at=verification.expires_at,
        created_at=verification.created_at,
        consumed_at=verification.consumed_at,
        verified_phone=verified_phone,
        verified_phone_masked=verified_phone_masked,
        failure_reason=verification.failure_reason,
    )


async def cancel_verification(
    session: AsyncSession,
    verification_id: UUID,
    *,
    market_id: UUID,
    actor_user_id: UUID,
    actor_is_market_admin: bool,
) -> None:
    verification = await session.scalar(
        select(WhatsAppVerification).where(
            WhatsAppVerification.id == verification_id,
            WhatsAppVerification.market_id == market_id,
        )
    )
    if verification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doğrulama kaydı bulunamadı.")
    if not (actor_is_market_admin or verification.user_id == actor_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yetkiniz bulunmuyor.",
        )

    if verification.status != "pending":
        return

    verification.status = "cancelled"
    verification.consumed_at = utc_now()


async def revoke_membership_whatsapp(
    session: AsyncSession,
    *,
    market_id: UUID,
    membership_id: UUID,
    actor_user_id: UUID,
    actor_is_market_admin: bool,
    reason: str | None,
) -> None:
    membership = await session.scalar(
        select(MarketUser).where(MarketUser.id == membership_id, MarketUser.market_id == market_id)
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Üye bulunamadı.")
    if not (actor_is_market_admin or membership.user_id == actor_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yetkiniz bulunmuyor.",
        )

    target_user_id = membership.user_id

    verified_identity = await session.scalar(
        select(UserWhatsAppIdentity).where(
            UserWhatsAppIdentity.user_id == target_user_id,
            UserWhatsAppIdentity.status == "verified",
        )
    )
    if verified_identity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bu üyenin doğrulanmış WhatsApp numarası yok.",
        )

    # A WhatsApp identity is global to the user (one identity, N markets), so
    # revoking it here would also cut that user's WhatsApp access to every
    # OTHER market they belong to — markets this admin has no authority over.
    # That blast radius is also unnecessary: removing/deactivating the
    # membership already stops the user acting on THIS market, because every
    # command re-resolves membership. So an admin acting on someone else is
    # refused when other active markets are involved; the user may always
    # revoke their own identity, and Platform Admin can revoke globally.
    if membership.user_id != actor_user_id:
        other_market_count = await session.scalar(
            select(func.count())
            .select_from(MarketUser)
            .join(Market, Market.id == MarketUser.market_id)
            .where(
                MarketUser.user_id == target_user_id,
                MarketUser.market_id != market_id,
                MarketUser.is_active.is_(True),
                Market.is_active.is_(True),
            )
        )
        if other_market_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Bu kullanıcı başka marketlere de bağlı olduğu için WhatsApp doğrulaması "
                    "buradan kaldırılamaz. Bu marketteki erişimi kesmek için kullanıcıyı ekipten "
                    "çıkarabilir veya pasife alabilirsiniz."
                ),
            )

    now = utc_now()
    verified_identity.status = "revoked"
    verified_identity.revoked_at = now
    verified_identity.revoked_reason = (reason or "").strip()[:255] or None
    verified_identity.revoked_by_user_id = actor_user_id

    pending_rows = (
        await session.scalars(
            select(WhatsAppVerification).where(
                WhatsAppVerification.user_id == target_user_id,
                WhatsAppVerification.status == "pending",
            )
        )
    ).all()
    for pending_row in pending_rows:
        pending_row.status = "cancelled"
        pending_row.consumed_at = now
        pending_row.failure_reason = "identity_revoked"

    await session.execute(delete(WhatsAppSession).where(WhatsAppSession.user_id == target_user_id))

    session.add(
        ActivityLog(
            market_id=market_id,
            user_id=actor_user_id,
            entity_type="whatsapp_verification",
            entity_id=verified_identity.id,
            action="WHATSAPP_VERIFICATION_REVOKED",
            description="WhatsApp verification revoked",
            metadata_={
                "target_user_id": str(target_user_id),
                "verified_phone_masked": mask_phone(verified_identity.phone_e164),
            },
        )
    )


def build_whatsapp_deep_link(official_number_e164: str, code: str) -> str:
    digits = official_number_e164.lstrip("+")
    return f"https://wa.me/{digits}?text={quote(code)}"
