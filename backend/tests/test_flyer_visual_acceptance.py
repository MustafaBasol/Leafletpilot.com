from __future__ import annotations

import io
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader

from app.core.config import settings
from app.services.image_pipeline import store_flyer_image
from app.services.preview_renderer import render_render_payload_html


FIXED_TIME = datetime(2026, 8, 7, 9, 30, tzinfo=UTC)


def _asset_bytes(kind: str) -> tuple[bytes, str]:
    if kind == "photo":
        image = Image.new("RGB", (900, 520), "#d8eef7")
        draw = ImageDraw.Draw(image)
        draw.rectangle((90, 70, 810, 450), fill="#f6d365")
        draw.ellipse((340, 110, 560, 430), fill="#d62828")
        image_format, mime_type = "JPEG", "image/jpeg"
    else:
        sizes = {"portrait": (480, 900), "landscape": (900, 480), "square": (700, 700)}
        width, height = sizes[kind]
        image = Image.new("RGBA", (width + 300, height + 300), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((150, 150, width + 150, height + 150), radius=45, fill="#ef233c")
        draw.rectangle((210, 230, width + 90, height - 30), fill="#ffffff")
        image_format, mime_type = "PNG", "image/png"
    output = io.BytesIO()
    image.save(output, format=image_format, quality=94)
    return output.getvalue(), mime_type


def _fixture_items(tmp_path: Path) -> list[dict]:
    items: list[dict] = []
    for kind in ("portrait", "landscape", "square", "photo"):
        content, mime_type = _asset_bytes(kind)
        asset = store_flyer_image(
            namespace=f"markets/visual-fixture/catalog/{kind}",
            original_content=content,
            declared_mime_type=mime_type,
        )
        items.append(
            {
                "name": f"{kind.title()} packaging",
                "brand": "Leaflet Fixture",
                "image_key": asset.storage_key,
                "image_mime_type": asset.mime_type,
                "image_has_alpha": asset.has_alpha,
                "price": "12.99",
                "old_price": "17.49",
                "currency": "EUR",
                "quantity_label": "2 x 500g",
                "badge": "25% OFF",
            }
        )
    return items


@pytest.mark.parametrize(("slug", "count"), [
    ("supermarket-promo-4", 4),
    ("supermarket-promo-9", 9),
    ("supermarket-promo-16", 16),
])
def test_real_chromium_flyers_fit_a4_without_collisions(
    slug: str, count: int, tmp_path: Path, monkeypatch
) -> None:
    storage_root = Path(os.environ.get("FLYER_VISUAL_STORAGE_DIR", tmp_path / "storage"))
    monkeypatch.setattr(settings, "local_storage_dir", str(storage_root))
    base = _fixture_items(tmp_path)
    items = []
    currencies = ("EUR", "TRY", "USD", "GBP", "CHF")
    for index in range(count):
        item = dict(base[index % len(base)])
        item["name"] = (
            "Extra long family-size supermarket product name that must remain readable"
            if index == 0
            else f"{item['name']} {index + 1}"
        )
        item["currency"] = currencies[index % len(currencies)]
        if index == 1:
            item["quantity_label"] = "Extra long family package label 12 x 750 mL recyclable bottles"
        if index == 2:
            item.pop("old_price", None)
        if index == count - 1:
            item.pop("image_key", None)
            item.pop("image_mime_type", None)
            item.pop("image_has_alpha", None)
            item["price"] = "999999.99"
            item["currency"] = "CHF"
        items.append(item)
    payload = {
        "template_slug": slug,
        "market_id": "visual-fixture",
        "market_name": "Fixture Market",
        "title": "Professional weekly offers",
        "header": {"validity_text": "07–13 August 2026"},
        "items": items,
    }
    html = render_render_payload_html(payload, generated_at=FIXED_TIME)
    assert html == render_render_payload_html(payload, generated_at=FIXED_TIME)

    artifact_root = Path(os.environ.get("FLYER_VISUAL_ARTIFACT_DIR", tmp_path / "artifacts"))
    artifact_root.mkdir(parents=True, exist_ok=True)
    png_path = artifact_root / f"{slug}.png"
    second_png_path = artifact_root / f"{slug}-repeat.png"
    pdf_path = artifact_root / f"{slug}.pdf"
    html_path = artifact_root / f"{slug}.html"
    html_path.write_text(html, encoding="utf-8")

    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except PlaywrightError as exc:
                pytest.skip(f"Playwright Chromium unavailable: {exc}")
            try:
                page = browser.new_page(viewport={"width": 1240, "height": 1754}, device_scale_factor=2)
                page.set_content(html, wait_until="networkidle")
                measurements = page.evaluate(
                    """() => {
                      const rect = (element) => {
                        const value = element.getBoundingClientRect();
                        return {left: value.left, top: value.top, right: value.right, bottom: value.bottom};
                      };
                      const overlaps = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
                      const documentBox = rect(document.querySelector('.preview-document'));
                      const grid = document.querySelector('.product-grid');
                      const gridBox = rect(grid);
                      const footer = document.querySelector('.footer');
                      const cards = [...document.querySelectorAll('.product-card')];
                      return {
                        viewport: {width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight},
                        cardCount: cards.length,
                        cardsInside: cards.every((card) => {
                          const box = rect(card);
                          return box.left >= documentBox.left && box.top >= documentBox.top && box.right <= documentBox.right && box.bottom <= documentBox.bottom;
                        }),
                        gridInside: gridBox.left >= documentBox.left && gridBox.right <= documentBox.right && gridBox.bottom <= documentBox.bottom,
                        footerAfterGrid: !footer || rect(footer).top >= gridBox.bottom,
                        noCardOverflow: cards.every((card) => card.scrollWidth <= card.clientWidth && card.scrollHeight <= card.clientHeight),
                        noStageTextCollision: cards.every((card) => {
                          const stage = rect(card.querySelector('.promo-card-image'));
                          const name = rect(card.querySelector('.product-name'));
                          const price = rect(card.querySelector('.price-panel'));
                          return !overlaps(stage, name) && !overlaps(stage, price) && !overlaps(name, price);
                        }),
                        badgesInside: [...document.querySelectorAll('.promo-badge')].every((badge) => {
                          const badgeBox = rect(badge);
                          const cardBox = rect(badge.closest('.product-card'));
                          return badgeBox.left >= cardBox.left && badgeBox.right <= cardBox.right && badgeBox.top >= cardBox.top && badgeBox.bottom <= cardBox.bottom;
                        }),
                        pricesInside: [...document.querySelectorAll('.price')].every((price) => {
                          const priceBox = rect(price);
                          const panelBox = rect(price.closest('.price-panel'));
                          return priceBox.left >= panelBox.left && priceBox.right <= panelBox.right && priceBox.top >= panelBox.top && priceBox.bottom <= panelBox.bottom;
                        }),
                        titlesClamped: [...document.querySelectorAll('.product-name')].every((title) => {
                          const style = getComputedStyle(title);
                          return style.getPropertyValue('-webkit-line-clamp') === '2' && style.overflow === 'hidden';
                        }),
                        imagesLoaded: [...document.images].every((image) => image.complete && image.naturalWidth > 0),
                        imagesContained: [...document.querySelectorAll('.product-image')].every((image) => getComputedStyle(image).objectFit === 'contain'),
                        fallbackCount: document.querySelectorAll('.image-placeholder').length,
                        densityProfile: document.querySelector('.preview-document').dataset.densityProfile,
                      };
                    }"""
                )
                assert measurements == {
                    "viewport": {"width": 1240, "height": 1754},
                    "cardCount": count,
                    "cardsInside": True,
                    "gridInside": True,
                    "footerAfterGrid": True,
                    "noCardOverflow": True,
                    "noStageTextCollision": True,
                    "badgesInside": True,
                    "pricesInside": True,
                    "titlesClamped": True,
                    "imagesLoaded": True,
                    "imagesContained": True,
                    "fallbackCount": 1,
                    "densityProfile": {4: "editorial", 9: "weekly", 16: "compact"}[count],
                }
                page.screenshot(path=str(png_path), clip={"x": 0, "y": 0, "width": 1240, "height": 1754})
                page.screenshot(path=str(second_png_path), clip={"x": 0, "y": 0, "width": 1240, "height": 1754})
                page.pdf(path=str(pdf_path), format="A4", print_background=True, scale=0.635)
            finally:
                browser.close()
    except ImportError as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    assert png_path.read_bytes() == second_png_path.read_bytes()
    with Image.open(png_path) as png:
        assert png.size == (2480, 3508)
    pdf = PdfReader(str(pdf_path))
    assert len(pdf.pages) == 1
    assert abs(float(pdf.pages[0].mediabox.width) - 595.276) < 2
    assert abs(float(pdf.pages[0].mediabox.height) - 841.89) < 2
