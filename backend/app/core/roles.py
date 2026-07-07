from enum import StrEnum


class MarketRole(StrEnum):
    MARKET_ADMIN = "market_admin"
    MARKET_STAFF = "market_staff"
    VIEWER = "viewer"


MARKET_USER_ROLES = tuple(role.value for role in MarketRole)
MARKET_MUTATION_ROLES = (MarketRole.MARKET_ADMIN.value, MarketRole.MARKET_STAFF.value)
MARKET_READ_ROLES = MARKET_USER_ROLES


ROLE_PERMISSION_MATRIX = {
    MarketRole.MARKET_ADMIN.value: (
        "read_market_data",
        "mutate_campaigns",
        "mutate_catalog",
        "mutate_templates",
        "create_exports",
        "download_files",
        "manage_team",
        "manage_invitations",
    ),
    MarketRole.MARKET_STAFF.value: (
        "read_market_data",
        "mutate_campaigns",
        "mutate_catalog",
        "create_exports",
        "download_files",
    ),
    MarketRole.VIEWER.value: (
        "read_market_data",
        "download_files",
    ),
}
