"""Evolution API webhook endpoint for the central LeafletPilot WhatsApp number.

Kept deliberately thin: authenticate, bound, parse, hand off. Everything that
decides identity, authorization or business effect lives in
`app/integrations/whatsapp/service.py`.

**Why a shared-secret header rather than a signature.** Evolution API does not
sign its webhook bodies — there is no HMAC digest to verify. What it does
support is a configurable set of headers sent with every delivery
(`webhook.headers`), so the strongest control compatible with the deployed
version is an unguessable server-side secret presented in a header and
compared in constant time. Network-level restriction (only Evolution's host
may reach this path) is documented as defence in depth in
`docs/backend/10_WHATSAPP_EVOLUTION_SETUP.md`, but is never the sole check:
the secret alone must be sufficient, because reverse-proxy topologies change.
"""

from __future__ import annotations

import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session
from app.core.config import settings
from app.integrations.whatsapp.schemas import normalize_evolution_event
from app.services.rate_limit import WHATSAPP_IP_KEY, consume_rate_limit, prune_expired_rate_limits

router = APIRouter(prefix="/webhooks/evolution", tags=["whatsapp"])

logger = logging.getLogger(__name__)

# Evolution only ever posts JSON metadata to this endpoint (media is fetched
# separately), so anything larger than this is not a payload we handle.
MAX_WEBHOOK_BODY_BYTES = 256 * 1024

WEBHOOK_TOKEN_HEADER = "x-evolution-webhook-token"


@router.post("/whatsapp")
async def evolution_whatsapp_webhook(request: Request) -> dict[str, object]:
    if not settings.evolution_whatsapp_enabled:
        # Same 404 the Telegram webhook uses when its integration is off: a
        # disabled channel should not advertise that the route exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    if not _valid_webhook_token(request):
        # No detail about which header was wrong or whether one was present.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")

    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            if int(declared_length) > MAX_WEBHOOK_BODY_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Payload too large.",
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Length header."
            ) from exc

    body = await request.body()
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large."
        )

    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        # Not JSON at all: this is not Evolution, so it is a client error.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload.") from exc

    normalized = normalize_evolution_event(payload)
    if normalized is None:
        # Structurally unusable but well-formed JSON. Acknowledge so Evolution
        # does not enter a redelivery loop over something we will never act on.
        return {"ok": True, "ignored": "unsupported_payload"}

    session_dependency = request.app.dependency_overrides.get(get_catalog_session, get_catalog_session)
    outcome = "ignored"
    async for session in session_dependency():
        if await _is_rate_limited(session, request):
            logger.warning("Evolution webhook rate limit hit for a client address.")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests."
            )
        outcome = await _process(request, session, normalized)
    return {"ok": True, "outcome": outcome}


async def _process(request: Request, session: AsyncSession, normalized) -> str:
    from app.integrations.whatsapp.service import process_webhook_event

    client_dependency = request.app.dependency_overrides.get(
        get_evolution_webhook_client, get_evolution_webhook_client
    )
    async for client in client_dependency():
        return await process_webhook_event(session, normalized, client)
    return "ignored"


async def get_evolution_webhook_client():
    """Outbound client used for webhook replies.

    Separate from the Platform Admin dependency so a test can override the
    inbound reply path without also stubbing the admin connection test.
    """
    from app.integrations.whatsapp.client import build_evolution_client

    client = build_evolution_client()
    try:
        yield client
    finally:
        await client.aclose()


async def _is_rate_limited(session: AsyncSession, request: Request) -> bool:
    await prune_expired_rate_limits(session)
    limited = await consume_rate_limit(
        session,
        key_type=WHATSAPP_IP_KEY,
        raw_value=_client_address(request),
        limit=settings.whatsapp_webhook_ip_limit,
    )
    await session.commit()
    return limited


def _valid_webhook_token(request: Request) -> bool:
    """Constant-time comparison against the configured webhook secret.

    Accepts the dedicated header or an `Authorization: Bearer` value, because
    which of the two an Evolution deployment can be configured to send varies
    by version and by whether a reverse proxy rewrites headers. Both are
    compared against the same secret with `hmac.compare_digest` over bytes
    (the str overload rejects non-ASCII input).
    """
    expected = settings.evolution_webhook_secret.strip()
    if not expected:
        return False
    expected_bytes = expected.encode("utf-8")

    candidates = []
    header_token = request.headers.get(WEBHOOK_TOKEN_HEADER)
    if header_token:
        candidates.append(header_token.strip())
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        candidates.append(value.strip())

    matched = False
    for candidate in candidates:
        # No short-circuit: every candidate is compared so the number of
        # comparisons does not depend on which one matched.
        if hmac.compare_digest(candidate.encode("utf-8"), expected_bytes):
            matched = True
    return matched


def _client_address(request: Request) -> str:
    """Client address, honouring X-Forwarded-For only behind a trusted proxy.

    Reuses the public-signup implementation rather than restating it: this is
    the rule that stops an untrusted caller from spoofing its way into a fresh
    rate-limit bucket by setting the header itself (including the CIDR
    handling for `TRUSTED_PROXY_IPS`), and two copies of it would eventually
    drift apart. The import is read-only; `public.py` is unchanged.
    """
    from app.api.routes.public import _client_address as resolve_client_address

    return resolve_client_address(request)
