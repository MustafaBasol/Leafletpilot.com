from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    market_id: UUID
    provider: str
    provider_chat_id: str
    status: str
    current_campaign_id: UUID | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
