"""Shared exception types for the billing service package."""

from __future__ import annotations


class BillingError(Exception):
    """A billing request could not be satisfied; safe to surface to the caller."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class WebhookSignatureError(Exception):
    """The inbound webhook request failed Stripe signature verification."""


class PermanentSyncError(Exception):
    """A webhook/resync payload can never be applied (unmapped price, orphaned
    customer, malformed payload, ...). Recorded as a sync error and surfaced
    to Platform Admin rather than retried by Stripe.

    ``market_id`` is carried separately (not read off any ORM object) because
    the caller rolls back the transaction before recording this failure —
    any ORM object referenced from inside the failed transaction is expired
    by that rollback.
    """

    def __init__(self, message: str, *, market_id=None) -> None:
        super().__init__(message)
        self.market_id = market_id
