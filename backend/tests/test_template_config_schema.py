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
