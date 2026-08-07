from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from PIL import Image, ImageDraw

from app.api.routes import catalog as catalog_routes
from app.api.routes import platform_catalog as platform_catalog_routes
from app.core.config import settings
from app.models import Campaign, CampaignItem, Market, MarketProduct, Product, ProductImage, Template
from app.services import rendering
from app.services.image_pipeline import (
    MAX_FLYER_EDGE,
    normalize_flyer_image,
    store_flyer_image,
    stored_flyer_image_has_alpha,
)
from app.services.preview_renderer import render_campaign_preview_html, render_render_payload_html


def _encode(image: Image.Image, image_format: str, **save_options) -> bytes:
    output = io.BytesIO()
    image.save(output, format=image_format, **save_options)
    return output.getvalue()


def _live_image_html(*, market_asset=None, global_asset=None, global_has_alpha=None) -> str:
    market = Market(id=uuid4(), name="Image Market", slug=f"image-market-{uuid4().hex}")
    global_image = (
        ProductImage(
            storage_key=global_asset.storage_key,
            mime_type=global_asset.mime_type,
            has_transparent_background=global_has_alpha,
            quality_status="good",
            is_primary=True,
        )
        if global_asset
        else None
    )
    product = Product(
        id=uuid4(),
        name="Image Product",
        is_global=True,
        images=[global_image] if global_image else [],
    )
    market_product = MarketProduct(
        id=uuid4(),
        market_id=market.id,
        product_id=product.id,
        product=product,
        image_storage_key=market_asset.storage_key if market_asset else None,
        image_mime_type=market_asset.mime_type if market_asset else None,
    )
    item = CampaignItem(
        id=uuid4(),
        market_id=market.id,
        raw_line="Image Product 4.99",
        incoming_name="Image Product",
        display_name="Image Product",
        match_status="matched",
        price="4.99",
        currency="EUR",
        product=product,
        market_product=market_product if market_asset else None,
    )
    campaign = Campaign(
        id=uuid4(),
        market_id=market.id,
        market=market,
        title="Image Campaign",
        language="en",
        currency="EUR",
        items=[item],
    )
    template = Template(name="Premium Market", slug="premium-market", config_json={"layout": "premium-market"})
    return render_campaign_preview_html(campaign, template, generated_at=datetime(2026, 8, 7, tzinfo=UTC))


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


@pytest.mark.parametrize(
    ("mode", "color", "expected_class"),
    [
        ("RGBA", (240, 30, 60, 180), "cutout"),
        ("RGB", (20, 90, 210), "photo"),
    ],
)
def test_market_override_uses_alpha_from_normalized_asset(
    tmp_path, monkeypatch, mode, color, expected_class
) -> None:
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    asset = store_flyer_image(
        namespace="markets/market-a/catalog/product-a",
        original_content=_encode(Image.new(mode, (80, 120), color), "PNG"),
        declared_mime_type="image/png",
    )

    html = _live_image_html(market_asset=asset)

    assert stored_flyer_image_has_alpha(asset.storage_key) is (expected_class == "cutout")
    assert f'class="product-image {expected_class}"' in html


def test_global_transparent_image_metadata_remains_cutout(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    asset = store_flyer_image(
        namespace="global/catalog/product-a",
        original_content=_encode(Image.new("RGBA", (80, 120), (240, 30, 60, 180)), "PNG"),
        declared_mime_type="image/png",
    )

    html = _live_image_html(global_asset=asset, global_has_alpha=True)

    assert 'class="product-image cutout"' in html


def test_missing_or_legacy_alpha_metadata_remains_safe(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    asset = store_flyer_image(
        namespace="markets/market-a/catalog/legacy-product",
        original_content=_encode(Image.new("RGB", (80, 120), (20, 90, 210)), "PNG"),
        declared_mime_type="image/png",
    )
    payload = {
        "template_slug": "premium-market",
        "items": [{"name": "Legacy product", "image_key": asset.storage_key, "image_mime_type": asset.mime_type}],
    }

    html = render_render_payload_html(payload, generated_at=datetime(2026, 8, 7, tzinfo=UTC))

    assert stored_flyer_image_has_alpha("markets/missing/legacy.png") is None
    assert 'class="product-image photo"' in html


def _request_that_must_not_stream(content_type: str) -> Request:
    async def receive():
        raise AssertionError("unsupported MIME body was streamed")

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/image",
            "query_string": b"",
            "headers": [(b"content-type", content_type.encode())],
        },
        receive,
    )


@pytest.mark.asyncio
async def test_platform_upload_rejects_unsupported_mime_before_stream(monkeypatch) -> None:
    product_id = uuid4()

    async def global_product(*_args):
        return Product(id=product_id, name="Platform Product", is_global=True)

    monkeypatch.setattr(platform_catalog_routes, "_global", global_product)

    with pytest.raises(HTTPException) as error:
        await platform_catalog_routes.upload_image(
            product_id,
            _request_that_must_not_stream("image/gif"),
            session=object(),
        )

    assert error.value.status_code == 415
    assert error.value.detail == "Only PNG, JPEG, and WebP images are allowed."


@pytest.mark.asyncio
async def test_market_upload_rejects_unsupported_mime_before_stream() -> None:
    with pytest.raises(HTTPException) as error:
        await catalog_routes.upload_market_image(
            uuid4(),
            _request_that_must_not_stream("image/gif"),
            market_id=uuid4(),
            session=object(),
        )

    assert error.value.status_code == 415
    assert error.value.detail == "Only PNG, JPEG, and WebP images are allowed."


@pytest.mark.asyncio
async def test_shared_image_content_disables_caching(tmp_path, monkeypatch) -> None:
    market = Market(
        id=uuid4(),
        name="Shared Image Market",
        slug=f"shared-image-{uuid4().hex}",
        subscription_plan="growth",
    )
    product = Product(
        id=uuid4(),
        name="Shared Image Product",
        is_global=True,
        images=[ProductImage(storage_key="global/catalog/image.png", mime_type="image/png", is_primary=True)],
    )
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")

    class Session:
        async def get(self, model, item_id):
            return market

        async def scalar(self, statement):
            return product

    monkeypatch.setattr(rendering, "storage_path_for_key", lambda _key: image_path)

    response = await catalog_routes.shared_image_content(
        product.id, market_id=market.id, session=Session()
    )

    assert response.headers["cache-control"] == "no-store"


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
