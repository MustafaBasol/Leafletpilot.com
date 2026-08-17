from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_market_membership, require_market_admin
from app.core.config import settings
from app.models import MarketUser
from app.models.billing import MarketSubscription
from app.schemas.billing import (
    BillingActionResponse,
    BillingSubscriptionRead,
    ChangePlanRequest,
    ChangePlanResponse,
    CheckoutRequest,
    CheckoutResponse,
    InvoiceListRead,
    PortalResponse,
)
from app.services.billing import service as billing_service
from app.services.billing.errors import BillingError, WebhookSignatureError
from app.services.billing.webhook import construct_event, process_event
from app.services.plans import normalize_plan_code

router = APIRouter(prefix="/billing", tags=["billing"])

MAX_STRIPE_WEBHOOK_BODY_BYTES = 512 * 1024


def _http_error(exc: BillingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _stripe_error_to_http(exc: "stripe.error.StripeError") -> HTTPException:
    """Translates a raised Stripe API error (bad request params, missing
    restricted-key permission, rate limit, network blip, ...) into a normal
    JSON error response instead of letting it escape as an unhandled 500.
    An unhandled exception here previously reached the browser as a
    misleading CORS failure rather than a readable API error — the request
    never actually left the origin, but a crashed handler can skip the
    response path that attaches CORS headers.

    Only ``stripe.error.StripeError`` (a *known* Stripe-side failure) is
    translated; anything else is a programmer bug and must keep propagating
    as an unhandled 500 so it isn't silently swallowed. No Stripe request
    payload, key, or internal trace is included in the message.
    """
    if isinstance(exc, stripe.error.AuthenticationError | stripe.error.PermissionError):
        detail = "Faturalandırma sağlayıcısı yapılandırması eksik veya yetkisiz. Lütfen destek ile iletişime geçin."
        status_code = 502
    elif isinstance(exc, stripe.error.RateLimitError | stripe.error.APIConnectionError):
        detail = "Faturalandırma sağlayıcısına şu anda ulaşılamıyor. Lütfen tekrar deneyin."
        status_code = 503
    else:
        # InvalidRequestError and anything else Stripe-side: the request as
        # built was rejected — not something the customer can fix by retrying
        # with different input, but also not proof of a local outage.
        detail = "Faturalandırma isteği işlenemedi. Lütfen tekrar deneyin veya destek ile iletişime geçin."
        status_code = 502
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/subscription", response_model=BillingSubscriptionRead)
async def get_subscription(
    membership: MarketUser = Depends(get_current_market_membership),
    session: AsyncSession = Depends(get_catalog_session),
) -> BillingSubscriptionRead:
    row = await session.scalar(
        select(MarketSubscription).where(MarketSubscription.market_id == membership.market_id)
    )
    if row is None:
        # No Stripe subscription has ever been created for this market yet —
        # fall back to the market's raw plan code, normalized so a legacy
        # alias (e.g. "growth") displays as its canonical plan ("standard")
        # rather than literally, since a real MarketSubscription row (below)
        # only ever stores canonical codes.
        return BillingSubscriptionRead(plan_code=normalize_plan_code(membership.market.subscription_plan))
    return BillingSubscriptionRead.model_validate(row)


@router.get("/invoices", response_model=InvoiceListRead)
async def list_invoices(
    limit: int = Query(default=20, ge=1, le=100),
    starting_after: str | None = Query(default=None),
    membership: MarketUser = Depends(get_current_market_membership),
    session: AsyncSession = Depends(get_catalog_session),
) -> InvoiceListRead:
    try:
        result = await billing_service.list_invoices(
            session, membership.market, limit=limit, starting_after=starting_after
        )
    except BillingError as exc:
        raise _http_error(exc) from exc
    except stripe.error.StripeError as exc:
        raise _stripe_error_to_http(exc) from exc
    return InvoiceListRead(**result)


@router.post("/checkout", response_model=CheckoutResponse)
async def start_checkout(
    payload: CheckoutRequest,
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> CheckoutResponse:
    try:
        result = await billing_service.create_checkout_session(
            session, membership.market, payload.plan_code, fallback_customer_email=membership.user.email
        )
    except BillingError as exc:
        raise _http_error(exc) from exc
    except stripe.error.StripeError as exc:
        raise _stripe_error_to_http(exc) from exc
    return CheckoutResponse(**result)


@router.post("/portal", response_model=PortalResponse)
async def open_portal(
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> PortalResponse:
    try:
        result = await billing_service.create_portal_session(session, membership.market)
    except BillingError as exc:
        raise _http_error(exc) from exc
    except stripe.error.StripeError as exc:
        raise _stripe_error_to_http(exc) from exc
    return PortalResponse(**result)


@router.post("/change-plan", response_model=ChangePlanResponse)
async def change_plan(
    payload: ChangePlanRequest,
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> ChangePlanResponse:
    try:
        result = await billing_service.change_plan(session, membership.market, payload.plan_code)
    except BillingError as exc:
        raise _http_error(exc) from exc
    except stripe.error.StripeError as exc:
        raise _stripe_error_to_http(exc) from exc
    return ChangePlanResponse(**result)


@router.post("/cancel", response_model=BillingActionResponse)
async def cancel_subscription(
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> BillingActionResponse:
    try:
        result = await billing_service.cancel_subscription(session, membership.market)
    except BillingError as exc:
        raise _http_error(exc) from exc
    except stripe.error.StripeError as exc:
        raise _stripe_error_to_http(exc) from exc
    return BillingActionResponse(**result)


@router.post("/resume", response_model=BillingActionResponse)
async def resume_subscription(
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> BillingActionResponse:
    try:
        result = await billing_service.resume_subscription(session, membership.market)
    except BillingError as exc:
        raise _http_error(exc) from exc
    except stripe.error.StripeError as exc:
        raise _stripe_error_to_http(exc) from exc
    return BillingActionResponse(**result)


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, bool]:
    if not settings.stripe_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe billing is disabled.")

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Length header.") from exc
        if declared_length > MAX_STRIPE_WEBHOOK_BODY_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Webhook payload is too large.")
    body = await request.body()
    if len(body) > MAX_STRIPE_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Webhook payload is too large.")

    try:
        event = construct_event(body, stripe_signature)
    except WebhookSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    session_dependency = request.app.dependency_overrides.get(get_catalog_session, get_catalog_session)
    async for session in session_dependency():
        await process_event(session, event)
    return {"ok": True}
