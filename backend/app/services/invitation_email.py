from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OwnerInvitationEmail:
    to_email: str
    market_name: str
    role: str
    accept_url: str
    expires_at: datetime
    language: str


class InvitationEmailError(RuntimeError):
    pass


async def send_owner_invitation_email(message: OwnerInvitationEmail) -> None:
    if settings.invitation_email_delivery == "disabled":
        raise InvitationEmailError("Invitation email delivery is not configured.")
    if settings.invitation_email_delivery == "fake":
        logger.info("Owner invitation email accepted by fake mailer.", extra={"to_domain": message.to_email.split("@")[-1]})
        return
    raise InvitationEmailError("Unsupported invitation email delivery mode.")
