from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from PIL import Image, ImageDraw

from app.core.config import settings
from app.services.image_pipeline import MAX_FLYER_EDGE, normalize_flyer_image, store_flyer_image
from app.services.preview_renderer import render_render_payload_html


def _encode(image: Image.Image, image_format: str, **save_options) -> bytes:
    output = io.BytesIO()
    image.save(output, format=image_format, **save_options)
    return output.getvalue()


def test_transparent_cutout_is_trimmed_scaled_and_deterministic() -> None:
    source = Image.new("RGBA", (2400, 2000), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((900, 300, 1499, 1699), fill=(220, 20, 40, 255))
    content = _encode(source, "PNG")

    first = normalize_flyer_image(content, "image/png")
    second = normalize_flyer_image(content, "image/png")

    assert first == second
    assert first.mime_type == "image/png"
    assert first.has_alpha is True
    assert max(first.width, first.height) <= MAX_FLYER_EDGE
    assert first.height > first.width
    assert first.width < 900  # transparent canvas, not product pixels, was discarded


def test_exif_orientation_and_opaque_photo_normalization() -> None:
    source = Image.new("RGB", (80, 40), (18, 110, 180))
    exif = Image.Exif()
    exif[274] = 6
    content = _encode(source, "JPEG", quality=95, exif=exif)

    normalized = normalize_flyer_image(content, "image/jpeg")

    assert normalized.mime_type == "image/jpeg"
    assert normalized.has_alpha is False
    assert (normalized.width, normalized.height) == (40, 80)


@pytest.mark.parametrize(
    ("content", "mime_type", "detail"),
    [
        (b"not-an-image", "image/png", "invalid or corrupt"),
        (_encode(Image.new("RGB", (4, 4)), "PNG"), "image/jpeg", "does not match"),
        (_encode(Image.new("RGB", (4, 4)), "GIF"), "image/gif", "Only PNG"),
    ],
)
def test_invalid_corrupt_and_unsupported_content_fails_safely(
    content: bytes, mime_type: str, detail: str
) -> None:
    with pytest.raises(HTTPException) as error:
        normalize_flyer_image(content, mime_type)
    assert error.value.status_code in {415, 422}
    assert detail in str(error.value.detail)


def test_excessive_dimensions_are_rejected_before_full_decode() -> None:
    content = _encode(Image.new("RGB", (12_001, 1)), "PNG")
    with pytest.raises(HTTPException) as error:
        normalize_flyer_image(content, "image/png")
    assert error.value.status_code == 422
    assert "dimensions" in str(error.value.detail)


def test_storage_is_content_addressed_namespaced_and_preserves_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    content = _encode(Image.new("RGBA", (80, 120), (240, 30, 60, 180)), "PNG")

    first = store_flyer_image(
        namespace="markets/market-a/catalog/product-a",
        original_content=content,
        declared_mime_type="image/png",
    )
    second = store_flyer_image(
        namespace="markets/market-a/catalog/product-a",
        original_content=content,
        declared_mime_type="image/png",
    )

    assert first == second
    assert first.storage_key.startswith("markets/market-a/catalog/product-a/flyer/")
    assert first.source_storage_key.startswith("markets/market-a/catalog/product-a/source/")
    assert (tmp_path / first.storage_key).read_bytes()
    assert (tmp_path / first.source_storage_key).read_bytes() == content
    assert ".." not in first.storage_key


def test_frozen_snapshot_image_survives_source_product_replacement(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    original = _encode(Image.new("RGBA", (80, 120), (240, 30, 60, 180)), "PNG")
    replacement = _encode(Image.new("RGB", (160, 80), (20, 90, 210)), "JPEG")
    first = store_flyer_image(
        namespace="markets/market-a/catalog/product-a",
        original_content=original,
        declared_mime_type="image/png",
    )
    snapshot = {
        "template_slug": "supermarket-promo-4",
        "items": [{
            "name": "Frozen product",
            "image_key": first.storage_key,
            "image_mime_type": first.mime_type,
            "image_has_alpha": first.has_alpha,
            "price": "4.99",
            "currency": "EUR",
        }],
    }
    before = render_render_payload_html(snapshot, generated_at=datetime(2026, 8, 7, tzinfo=UTC))

    store_flyer_image(
        namespace="markets/market-a/catalog/product-a",
        original_content=replacement,
        declared_mime_type="image/jpeg",
    )
    after = render_render_payload_html(snapshot, generated_at=datetime(2026, 8, 7, tzinfo=UTC))

    assert before == after
    assert (tmp_path / first.storage_key).is_file()
