import pytest

from app.core.config import Settings
from app.scripts.demo_tenant import (
    DEMO_PRODUCTS,
    DemoOperationError,
    asset_source,
    require_demo_operations,
    stable_id,
)


def test_demo_operations_are_disabled_by_default():
    with pytest.raises(DemoOperationError, match="disabled"):
        require_demo_operations()


def test_stable_ids_and_dataset_are_deterministic():
    assert stable_id("campaign", "haftanin-super-firsatlari") == stable_id("campaign", "haftanin-super-firsatlari")
    assert len(DEMO_PRODUCTS) == 16
    assert all(barcode.startswith("LP-DEMO-") for _, _, _, _, barcode, _, _ in DEMO_PRODUCTS)
    assert [row[0] for row in DEMO_PRODUCTS] == [
        "apple", "banana", "tomato", "lettuce", "milk", "bread", "coffee", "pasta",
        "rice", "olive-oil", "cereal", "yogurt", "dish-soap", "detergent", "paper-towels", "beans",
    ]


def test_all_local_demo_assets_exist_and_are_pngs():
    for slug, *_ in DEMO_PRODUCTS:
        path = asset_source(slug)
        assert path.is_file(), slug
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert path.stat().st_size > 0


def test_enabled_settings_require_complete_allow_list():
    with pytest.raises(ValueError, match="DEMO_MARKET_ID"):
        Settings(DEMO_OPERATIONS_ENABLED=True, DEMO_MARKET_SLUG="demo", DEMO_OWNER_EMAIL="demo@example.test")
