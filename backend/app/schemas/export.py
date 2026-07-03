from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


CampaignFileType = Literal[
    "preview_png",
    "brochure_pdf",
    "brochure_png",
    "instagram_post",
    "instagram_story",
    "whatsapp_image",
    "source_upload",
]
CampaignFileStatus = Literal["pending", "generating", "ready", "failed", "sent"]
ExportJobType = Literal["preview", "final_export", "regenerate_preview", "send_files"]
ExportJobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class CampaignFileCreate(BaseModel):
    file_type: CampaignFileType
    format: str | None = Field(default=None, max_length=16)
    status: CampaignFileStatus = "pending"
    storage_key: str | None = Field(default=None, max_length=1000)
    url: str | None = Field(default=None, max_length=1000)
    size_bytes: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    error_message: str | None = None


class CampaignFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    market_id: UUID
    file_type: str
    format: str | None
    status: str
    storage_key: str | None
    url: str | None
    size_bytes: int | None
    page_number: int | None
    width: int | None
    height: int | None
    sent_to_user_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ExportJobCreate(BaseModel):
    job_type: ExportJobType
    requested_formats: list[str] | None = None
    status: ExportJobStatus = "queued"


class ExportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    market_id: UUID
    requested_by_user_id: UUID | None
    job_type: str
    status: str
    requested_formats: list[str] | None
    result_file_ids: list[str] | None
    error_message: str | None
    attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    updated_at: datetime
