"""Bucketed rate limiting shared by the WhatsApp channel.

Reuses the `signup_throttles` table and the exact counter semantics the public
signup endpoint already runs in production (fixed window bucket + hashed key +
`ON CONFLICT DO UPDATE ... RETURNING`), rather than introducing a second,
differently-behaving limiter. Keys are HMAC-hashed before storage, so a phone
number or user id never lands in the table in the clear.

The only schema change this required was widening
`ck_signup_throttles_key_type` to admit the WhatsApp key types (migration
20260817_0029); `app/api/routes/public.py` is untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_signup_throttle_key
from app.models import SignupThrottle
from app.models.base import utc_now

# Must match the CHECK constraint and stay within signup_throttles.key_type's
# 16-character column width.
WHATSAPP_IP_KEY = "whatsapp_ip"
WHATSAPP_USER_KEY = "whatsapp_user"
WHATSAPP_SENDER_KEY = "whatsapp_sender"
AI_USER_KEY = "ai_user"

# Buckets older than this many windows are pruned opportunistically, matching
# the public-signup cleanup policy.
_RETAINED_WINDOWS = 48


async def consume_rate_limit(
    session: AsyncSession,
    *,
    key_type: str,
    raw_value: str,
    limit: int,
    window_minutes: int | None = None,
    purpose: str = "whatsapp",
) -> bool:
    """Records one hit and returns True when the caller is now over `limit`.

    Never raises on contention: the upsert is atomic, so two concurrent
    requests both get a correct, distinct count.
    """
    window_seconds = max(1, (window_minutes or settings.whatsapp_rate_limit_window_minutes)) * 60
    now = utc_now()
    window_bucket = int(now.timestamp()) // window_seconds
    window_started_at = datetime.fromtimestamp(window_bucket * window_seconds, tz=UTC)
    key_hash = hash_signup_throttle_key(f"{purpose}:{key_type}:{raw_value}")
    statement = (
        insert(SignupThrottle)
        .values(
            key_type=key_type,
            key_hash=key_hash,
            window_bucket=window_bucket,
            window_started_at=window_started_at,
            request_count=1,
        )
        .on_conflict_do_update(
            constraint="uq_signup_throttles_type_key_bucket",
            set_={
                "request_count": SignupThrottle.request_count + 1,
                "updated_at": utc_now(),
            },
        )
        .returning(SignupThrottle.request_count)
    )
    count = int(await session.scalar(statement) or 1)
    return count > limit


# Last window bucket this process ran a prune for. The webhook is a
# high-frequency endpoint, so issuing the cleanup DELETE on every inbound
# message would add a scan per WhatsApp message for no benefit; once per
# window per process is plenty. Purely an optimisation — losing this state on
# restart just means one extra prune.
_last_pruned_bucket: int | None = None


async def prune_expired_rate_limits(session: AsyncSession, *, window_minutes: int | None = None) -> None:
    """Prunes only WhatsApp buckets, at most once per window per process.

    `window_bucket` is `timestamp // window_seconds`, so its magnitude depends
    on the window length: WhatsApp's 10-minute buckets number ~6x higher than
    the public-signup 60-minute buckets. Deleting by cutoff alone would
    therefore wipe every live signup-throttle row and silently disable that
    protection, so the delete is restricted to this module's key types.
    """
    global _last_pruned_bucket

    window_seconds = max(1, (window_minutes or settings.whatsapp_rate_limit_window_minutes)) * 60
    current_bucket = int(utc_now().timestamp()) // window_seconds
    if _last_pruned_bucket == current_bucket:
        return
    _last_pruned_bucket = current_bucket
    cutoff_bucket = current_bucket - _RETAINED_WINDOWS
    await session.execute(
        delete(SignupThrottle).where(
            SignupThrottle.key_type.in_((WHATSAPP_IP_KEY, WHATSAPP_USER_KEY, WHATSAPP_SENDER_KEY)),
            SignupThrottle.window_bucket < cutoff_bucket,
        )
    )


async def prune_expired_ai_rate_limits(session: AsyncSession) -> None:
    """Prune only old one-minute AI-user buckets without touching other limiters."""
    current_bucket = int(utc_now().timestamp()) // 60
    await session.execute(
        delete(SignupThrottle).where(
            SignupThrottle.key_type == AI_USER_KEY,
            SignupThrottle.window_bucket < current_bucket - _RETAINED_WINDOWS,
        )
    )
