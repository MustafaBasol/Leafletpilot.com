from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BrandBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    logo_url: str | None = Field(default=None, max_length=1000)
    is_global: bool = False
    is_active: bool = True


class BrandCreate(BrandBase):
    pass


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    logo_url: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


class BrandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    market_id: UUID | None
    name: str
    slug: str
    logo_url: str | None
    is_global: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
