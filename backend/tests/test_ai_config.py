import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_generic_and_image_timeout_defaults_are_independent() -> None:
    settings = Settings.model_validate({})

    assert settings.ai_http_timeout_seconds == 15
    assert settings.ai_image_http_timeout_seconds == 120


@pytest.mark.parametrize("value", [15, 120, 300])
def test_image_timeout_accepts_documented_bounds(value: int) -> None:
    settings = Settings.model_validate({"AI_IMAGE_HTTP_TIMEOUT_SECONDS": value})

    assert settings.ai_image_http_timeout_seconds == value


@pytest.mark.parametrize("value", [14, 301])
def test_image_timeout_rejects_values_outside_bounds(value: int) -> None:
    with pytest.raises(ValidationError, match="AI_IMAGE_HTTP_TIMEOUT_SECONDS"):
        Settings.model_validate({"AI_IMAGE_HTTP_TIMEOUT_SECONDS": value})


def test_generic_timeout_retains_sixty_second_ceiling() -> None:
    with pytest.raises(ValidationError, match="AI_HTTP_TIMEOUT_SECONDS"):
        Settings.model_validate({"AI_HTTP_TIMEOUT_SECONDS": 61})
