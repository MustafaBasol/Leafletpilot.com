from enum import StrEnum


class TelegramState(StrEnum):
    IDLE = "idle"
    AWAITING_MARKET = "awaiting_market"
    AWAITING_PRODUCT_LIST = "awaiting_product_list"
    AWAITING_TITLE = "awaiting_title"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    GENERATING_EXPORTS = "generating_exports"
    COMPLETED = "completed"
