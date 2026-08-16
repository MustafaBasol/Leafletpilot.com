from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BillingSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_code: str
    status: str | None = None
    pending_plan_code: str | None = None
    pending_change_at: datetime | None = None
    pending_change_reason: str | None = None
    currency: str | None = None
    unit_amount: int | None = None
    interval: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    canceled_at: datetime | None = None
    subscription_started_at: datetime | None = None
    last_payment_status: str | None = None
    last_payment_at: datetime | None = None
    sync_error: str | None = None


class CheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=32)


class CheckoutResponse(BaseModel):
    checkout_url: str
    checkout_session_id: str


class PortalResponse(BaseModel):
    portal_url: str


class ChangePlanRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=32)


class ChangePlanResponse(BaseModel):
    status: str
    expires_at: datetime | None = None
    effective_at: datetime | None = None


class BillingActionResponse(BaseModel):
    status: str


class InvoiceRead(BaseModel):
    invoice_id: str | None
    number: str | None
    created_at: datetime | None
    period_start: datetime | None
    period_end: datetime | None
    subtotal: int | None
    total: int | None
    amount_paid: int | None
    amount_due: int | None
    currency: str | None
    status: str | None
    payment_failed: bool
    paid_at: datetime | None
    hosted_invoice_url: str | None
    invoice_pdf: str | None


class InvoiceListRead(BaseModel):
    items: list[InvoiceRead]
    has_more: bool
