import pytest
from pydantic import ValidationError

from app.schemas.template import TemplateConfig, TemplateUpdate


def test_full_template_config_is_validated():
    config = TemplateConfig(
        layout="promo-9", columns=3, rows=3, slot_count=9,
        page_format="a4_portrait", primary_color="#112233", secondary_color="#ffffff",
        price_style="panel", badge_style="burst",
    )
    assert config.slot_count == 9


def test_legacy_capacity_is_normalized_and_invalid_values_are_turkish():
    with pytest.raises(ValidationError, match="Ürün kapasitesi 4, 6, 9, 12 veya 16 olmalıdır"):
        TemplateConfig(slot_count=8)
    with pytest.raises(ValidationError):
        TemplateConfig(primary_color="red")


def test_partial_config_only_serializes_submitted_fields():
    payload = TemplateUpdate(config_json={"show_footer": False})
    assert payload.config_json.model_dump(exclude_unset=True) == {"show_footer": False}


def test_legacy_supported_capacity_gets_canonical_grid():
    config = TemplateConfig(slot_count=9)
    assert (config.layout, config.columns, config.rows) == ("promo-9", 3, 3)


@pytest.mark.parametrize("layout", ["premium-market", "compact-weekly"])
def test_legacy_renderer_families_remain_valid(layout):
    config = TemplateConfig(layout=layout, slot_count=4)
    assert config.layout == layout
    assert config.grid_preset == "promo-4"


@pytest.mark.parametrize(
    ("layout", "capacity"),
    [("supermarket-promo-4", 4), ("supermarket-promo-9", 9), ("supermarket-promo-16", 16)],
)
def test_supermarket_renderer_families_infer_their_grid(layout, capacity):
    config = TemplateConfig(layout=layout)
    assert config.layout == layout
    assert config.slot_count == capacity
    assert config.grid_preset == f"promo-{capacity}"


@pytest.mark.parametrize("capacity", [4, 6, 9, 12, 16])
def test_builder_grid_presets_validate(capacity):
    config = TemplateConfig(grid_preset=f"promo-{capacity}")
    assert config.slot_count == capacity
    assert config.columns * config.rows == capacity


def test_grid_dimension_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="sütun × satır"):
        TemplateConfig(layout="premium-market", slot_count=4, columns=3, rows=2)


def test_partial_update_preserves_explicit_legacy_renderer_key():
    payload = TemplateUpdate(config_json={"layout": "premium-market", "show_footer": False})
    assert payload.config_json.model_dump(exclude_unset=True) == {
        "layout": "premium-market",
        "show_footer": False,
    }


def test_supermarket_semantic_tokens_are_validated_without_arbitrary_css():
    config = TemplateConfig(
        layout="supermarket-promo-9",
        background_start="#123456", background_end="#234567", card_background="#fff8e7",
        card_border_color="#f1b900", price_panel_background="#ffd928", price_color="#c5161d",
        header_style="band", card_style="outlined", price_style="ticket",
        badge_style="ribbon", image_treatment="cutout", show_payment_icons=False,
    )
    assert config.slot_count == 9
    assert (config.header_style, config.card_style, config.price_style, config.badge_style) == (
        "band", "outlined", "ticket", "ribbon",
    )
    with pytest.raises(ValidationError):
        TemplateConfig(layout="supermarket-promo-4", background_start="red;position:fixed")
    with pytest.raises(ValidationError):
        TemplateConfig(layout="supermarket-promo-4", badge_style="custom-css")


def test_old_supermarket_config_gets_safe_semantic_defaults():
    config = TemplateConfig(layout="supermarket-promo-4", primary_color="#112233", secondary_color="#ffffff")
    assert config.header_style == "burst"
    assert config.card_style == "shadow"
    assert config.image_treatment == "stage"
    assert config.primary_color == "#112233"
