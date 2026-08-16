from pydantic import BaseModel


class PublicPlanRead(BaseModel):
    code: str
    name: str
    monthly_price: float | None
    currency: str
    tagline: str
    campaigns_per_month: int | None
    private_products_limit: int | None
    export_formats: list[str]
    support_tier: str
    custom_template: bool
    telegram_enabled: bool
    is_recommended: bool
    features: list[str]


class MarketPlanUsageRead(BaseModel):
    code: str
    name: str
    monthly_price: float | None
    currency: str
    monthly_campaigns_limit: int | None
    monthly_campaigns_used: int
    monthly_exports_limit: int | None
    private_products_limit: int | None
    private_templates_limit: int | None
    branding_assets_limit: int | None
    export_formats: list[str]
    support_tier: str
