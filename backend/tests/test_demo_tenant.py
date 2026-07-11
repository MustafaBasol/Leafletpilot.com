import pytest

from app.core.config import Settings
from app.scripts.demo_tenant import (
    DEMO_BRANDS,
    DEMO_PRODUCTS,
    DemoOperationError,
    asset_source,
    require_demo_operations,
    stable_id,
    safe_demo_storage_path,
)
from uuid import UUID


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


def test_demo_brand_fixtures_are_exact_and_unambiguous():
    assert len(DEMO_BRANDS) == 1
    assert DEMO_BRANDS == (
        {"key": "generic", "name": "LeafletPilot Demo", "slug": "demo-generic"},
    )
    assert all(len(fixture["name"]) > 1 for fixture in DEMO_BRANDS)
    assert len({fixture["slug"] for fixture in DEMO_BRANDS}) == len(DEMO_BRANDS)


def test_all_local_demo_assets_exist_and_are_pngs():
    for slug, *_ in DEMO_PRODUCTS:
        path = asset_source(slug)
        assert path.is_file(), slug
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert path.stat().st_size > 0


def test_enabled_settings_require_complete_allow_list():
    with pytest.raises(ValueError, match="DEMO_MARKET_ID"):
        Settings(DEMO_OPERATIONS_ENABLED=True, DEMO_MARKET_SLUG="demo", DEMO_OWNER_EMAIL="demo@example.test")


def test_demo_storage_deletion_rejects_roots_traversal_and_wrong_market(tmp_path, monkeypatch):
    from app.core.config import settings

    market_id = UUID("11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    (tmp_path / "markets" / str(market_id) / "demo-assets").mkdir(parents=True)
    with pytest.raises((ValueError, DemoOperationError)):
        safe_demo_storage_path(f"markets/{market_id}", market_id)
    with pytest.raises((ValueError, DemoOperationError)):
        safe_demo_storage_path(f"markets/{market_id}/../other/file", market_id)
    with pytest.raises(DemoOperationError):
        safe_demo_storage_path("markets/22222222-2222-2222-2222-222222222222/demo-assets/a.png", market_id)


def test_demo_storage_deletion_rejects_symlink_escape_when_supported(tmp_path, monkeypatch):
    from app.core.config import settings

    market_id = UUID("33333333-3333-3333-3333-333333333333")
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    scope = tmp_path / "markets" / str(market_id) / "demo-assets"
    scope.mkdir(parents=True)
    link = scope / "escape"
    try:
        link.symlink_to(tmp_path / "outside", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported by this test environment")
    with pytest.raises(DemoOperationError):
        safe_demo_storage_path(f"markets/{market_id}/demo-assets/escape/file.png", market_id)

def test_empty_demo_market_id_is_normalized_to_none():
    config = Settings(DEMO_MARKET_ID="")
    assert config.demo_market_id is None
