from __future__ import annotations

import io
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image, ImageChops, ImageDraw
from pypdf import PdfReader

from app.core.config import settings
from app.services.image_pipeline import store_flyer_image
from app.services.preview_renderer import render_render_payload_html
from app.services.rendering import render_html_to_pdf_sync, render_html_to_png_sync
from app.services.visual_quality_gate import QUALITY_THRESHOLD, run_visual_quality_gate

FIXED_TIME = datetime(2026, 8, 7, 9, 30, tzinfo=UTC)

REFERENCE_EXPECTATIONS = {
    4: {
        "density": "editorial",
        "featured": 1,
        "min_width_tiers": 2,
        "min_stage_delta": 500,
        "min_price_width_delta": 0.08,
        "min_featured_area_ratio": 2.5,
        "min_featured_image_ratio": 4.0,
        "min_featured_price_ratio": 1.45,
        # Large-quad intentionally pairs one dominant hero stage with balanced support stages.
        "min_featured_stage_height_ratio": 3.0,
        "max_support_stage_height_range": 4.0,
        "min_price_patterns": 3,
        "min_price_ratio": 0.55,
    },
    9: {
        "density": "weekly",
        "featured": 1,
        "min_width_tiers": 2,
        "min_stage_delta": 40,
        "min_price_width_delta": 0.06,
        "min_featured_area_ratio": 1.55,
        "min_featured_image_ratio": 1.8,
        "min_featured_price_ratio": 1.15,
        "min_stage_tiers": 3,
        "min_price_patterns": 3,
        "min_lower_width_tiers": 3,
        "min_visual_price_treatments": 3,
        "min_perceptible_offsets": 5,
        "min_price_ratio": 0.38,
    },
    16: {
        "density": "compact",
        "featured": 1,
        "min_width_tiers": 2,
        "min_stage_delta": 20,
        "min_price_width_delta": 0.06,
        "min_featured_area_ratio": 0.99,
        "min_featured_image_ratio": 1.0,
        "min_featured_price_ratio": 1.0,
        "min_stage_tiers": 3,
        "min_price_patterns": 3,
        "min_visual_price_treatments": 4,
        "min_perceptible_offsets": 8,
        "min_price_ratio": 0.38,
    },
}


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
    product_names = {
        "portrait": "Extra virgin olive oil glass bottle",
        "landscape": "Family-size frozen pizza carton",
        "square": "Crispy breakfast cereal package",
        "photo": "Fresh strawberry photo product",
    }
    for kind in ("portrait", "landscape", "square", "photo"):
        content, mime_type = _asset_bytes(kind)
        asset = store_flyer_image(
            namespace=f"markets/visual-fixture/catalog/{kind}",
            original_content=content,
            declared_mime_type=mime_type,
        )
        items.append(
            {
                "name": product_names[kind],
                "brand": ("Orchard", "Bakery", "Morning", "Produce")[len(items)],
                "image_key": asset.storage_key,
                "image_mime_type": asset.mime_type,
                "image_has_alpha": asset.has_alpha,
                "price": ("12.99", "4.49", "2.79", "6.95")[len(items)],
                "old_price": "17.49",
                "currency": "EUR",
                "quantity_label": "2 x 500g",
                "badge": "25% OFF",
            }
        )
    return items


@pytest.mark.parametrize(
    ("slug", "count"),
    [
        ("supermarket-promo-4", 4),
        ("supermarket-promo-9", 9),
        ("supermarket-promo-16", 16),
    ],
)
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
            item["quantity_label"] = (
                "Extra long family package label 12 x 750 mL recyclable bottles"
            )
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
        "builder_config": {"smart_composition": True},
        "items": items,
    }
    html = render_render_payload_html(payload, generated_at=FIXED_TIME)
    assert html == render_render_payload_html(payload, generated_at=FIXED_TIME)

    artifact_root = Path(os.environ.get("FLYER_VISUAL_ARTIFACT_DIR", tmp_path / "artifacts"))
    artifact_root.mkdir(parents=True, exist_ok=True)
    png_path = artifact_root / f"{slug}-after.png"
    second_png_path = artifact_root / f"{slug}-after-repeat.png"
    pdf_path = artifact_root / f"{slug}.pdf"
    export_png_path = artifact_root / f"{slug}-export.png"
    repeat_export_png_path = artifact_root / f"{slug}-export-repeat.png"
    export_pdf_path = artifact_root / f"{slug}-export.pdf"
    html_path = artifact_root / f"{slug}.html"
    html_path.write_text(html, encoding="utf-8")

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except PlaywrightError as exc:
                pytest.skip(f"Playwright Chromium unavailable: {exc}")
            try:
                page = browser.new_page(
                    viewport={"width": 1240, "height": 1754}, device_scale_factor=2
                )
                page_errors: list[str] = []
                console_errors: list[str] = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                failed_requests: list[str] = []
                page.on(
                    "console",
                    lambda message: (
                        console_errors.append(message.text) if message.type == "error" else None
                    ),
                )
                page.set_content(html, wait_until="networkidle")
                page.on("requestfailed", lambda request: failed_requests.append(request.url))
                page.evaluate("""async () => {
                  await Promise.all([...document.images].map((image) => image.decode().catch(() => {})));
                  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                }""")
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
                      const stages = cards.map((card) => card.querySelector('.promo-card-image'));
                      const panels = cards.map((card) => card.querySelector('.price-panel'));
                      const featured = document.querySelector('[data-merchandising-role="featured"]');
                      const supporting = cards.filter((card) => card !== featured);
                      const area = (element) => {
                        const box = rect(element);
                        return (box.right - box.left) * (box.bottom - box.top);
                      };
                      const ratio = (numerator, denominator) => denominator ? numerator / denominator : null;
                      const hasVisibleSurface = (element) => {
                        const style = getComputedStyle(element);
                        return style.backgroundImage !== 'none' ||
                          !['rgba(0, 0, 0, 0)', 'transparent'].includes(style.backgroundColor);
                      };
                      const featuredStage = featured?.querySelector('.promo-card-image');
                      const featuredPrice = featured?.querySelector('.price');
                      const supportStageAreas = supporting.map((card) => area(card.querySelector('.promo-card-image')));
                      const supportStageHeights = supporting.map((card) => {
                        const box = rect(card.querySelector('.promo-card-image'));
                        return box.bottom - box.top;
                      });
                      const supportAreas = supporting.map(area);
                      const supportPriceSizes = supporting.map((card) => parseFloat(getComputedStyle(card.querySelector('.price')).fontSize));
                      const logicalRowSize = Number(document.querySelector('.preview-document').dataset.layout.split('x')[0]);
                      const logicalRows = Array.from(
                        {length: Math.ceil(cards.length / logicalRowSize)},
                        (_, row) => cards.slice(row * logicalRowSize, (row + 1) * logicalRowSize),
                      );
                      const topRange = (elements) => {
                        const tops = elements.map((element) => rect(element).top);
                        return Math.max(...tops) - Math.min(...tops);
                      };
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
                        compositionClass: [...document.querySelector('.preview-document').classList].find((value) => value.startsWith('composition-')),
                        featuredCount: document.querySelectorAll('.product-card[data-emphasis="featured"]').length,
                        cutoutStageCount: document.querySelectorAll('.promo-card-image[data-image-stage="cutout"]').length,
                        cardTopBordersReduced: cards.every((card) => parseFloat(getComputedStyle(card).borderTopWidth) <= 1),
                        heavyBorderSideCount: cards.reduce((total, card) => {
                          const style = getComputedStyle(card);
                          return total + ['Top', 'Right', 'Bottom', 'Left'].filter((side) => parseFloat(style[`border${side}Width`]) > 1).length;
                        }, 0),
                        roleCounts: cards.reduce((counts, card) => {
                          const role = card.dataset.merchandisingRole;
                          counts[role] = (counts[role] || 0) + 1;
                          return counts;
                        }, {}),
                        cardWidthTiers: [...new Set(cards.map((card) => Math.round(rect(card).right - rect(card).left)))].length,
                        stageHeightRange: Math.max(...stages.map((stage) => rect(stage).bottom - rect(stage).top)) - Math.min(...stages.map((stage) => rect(stage).bottom - rect(stage).top)),
                        priceWidthRatios: panels.map((panel) => ratio(rect(panel).right - rect(panel).left, rect(panel.closest('.product-card')).right - rect(panel.closest('.product-card')).left)),
                        pricePatternCount: new Set(panels.map((panel) => {
                          const card = panel.closest('.product-card');
                          return `${card.dataset.priceAlign}:${Math.round(ratio(rect(panel).right - rect(panel).left, rect(card).right - rect(card).left) * 20)}`;
                        })).size,
                        imageStageHeightTiers: new Set(stages.map((stage) => Math.round((rect(stage).bottom - rect(stage).top) / 4))).size,
                        imageTopTiers: new Set(stages.map((stage) => Math.round(rect(stage).top / 12))).size,
                        imageTierCount: new Set(cards.map((card) => card.dataset.imageTier)).size,
                        priceTreatmentCount: new Set(cards.map((card) => card.dataset.priceTreatment)).size,
                        priceTreatmentGeometryCount: new Set(panels.map((panel) => {
                          const style = getComputedStyle(panel);
                          const card = panel.closest('.product-card');
                          return [
                            card.dataset.priceTreatment,
                            style.backgroundColor,
                            style.backgroundImage,
                            Math.round(parseFloat(style.borderLeftWidth)),
                            Math.round(ratio(rect(panel).right - rect(panel).left, rect(card).right - rect(card).left) * 10),
                          ].join(':');
                        })).size,
                        perceptibleVerticalOffsetCount: cards.filter((card) => Number(card.dataset.verticalOffset) >= 12).length,
                        logicalRowImageTopRanges: logicalRows.map((row) => topRange(row.map((card) => card.querySelector('.promo-card-image')))),
                        logicalRowPriceTopRanges: logicalRows.map((row) => topRange(row.map((card) => card.querySelector('.price-panel')))),
                        noCardCollisions: cards.every((card, index) => cards.slice(index + 1).every((other) => !overlaps(rect(card), rect(other)))),
                        fullSeparatorCount: cards.reduce((total, card) => {
                          const style = getComputedStyle(card);
                          const box = rect(card);
                          const horizontal = (box.right - box.left) / (gridBox.right - gridBox.left);
                          const vertical = (box.bottom - box.top) / (gridBox.bottom - gridBox.top);
                          return total +
                            (parseFloat(style.borderTopWidth) > 0 && horizontal > .7 ? 1 : 0) +
                            (parseFloat(style.borderBottomWidth) > 0 && horizontal > .7 ? 1 : 0) +
                            (parseFloat(style.borderLeftWidth) > 0 && vertical > .7 ? 1 : 0) +
                            (parseFloat(style.borderRightWidth) > 0 && vertical > .7 ? 1 : 0);
                        }, 0),
                        enclosingBorderCount: cards.filter((card) => {
                          const style = getComputedStyle(card);
                          return ['Top', 'Right', 'Bottom', 'Left'].every((side) => parseFloat(style[`border${side}Width`]) > 0);
                        }).length,
                        secondaryEnclosingBorderCount: supporting.filter((card) => {
                          const style = getComputedStyle(card);
                          return ['Top', 'Right', 'Bottom', 'Left'].some((side) => parseFloat(style[`border${side}Width`]) > 0);
                        }).length,
                        sharedSectionSurface: hasVisibleSurface(grid),
                        opaqueCardCount: cards.filter(hasVisibleSurface).length,
                        lowerOpaqueCardCount: cards.slice(3).filter(hasVisibleSurface).length,
                        lowerCardWidthTiers: new Set(cards.slice(3).map((card) => Math.round(rect(card).right - rect(card).left))).size,
                        compositionGroups: new Set(cards.map((card) => card.dataset.compositionGroup)).size,
                        featuredAreaRatio: featured ? ratio(area(featured), Math.max(...supportAreas)) : null,
                        featuredImageRatio: featuredStage ? ratio(area(featuredStage), Math.max(...supportStageAreas)) : null,
                        featuredPriceRatio: featuredPrice ? ratio(parseFloat(getComputedStyle(featuredPrice).fontSize), Math.max(...supportPriceSizes)) : null,
                        featuredStageHeightRatio: featuredStage ? ratio(rect(featuredStage).bottom - rect(featuredStage).top, Math.max(...supportStageHeights)) : null,
                        supportStageHeightRange: Math.max(...supportStageHeights) - Math.min(...supportStageHeights),
                      };
                    }"""
                )
                reference = REFERENCE_EXPECTATIONS[count]
                evidence = {
                    "reference": reference,
                    "measurements": measurements,
                    "pageErrors": page_errors,
                    "consoleErrors": console_errors,
                    "failedRequests": failed_requests,
                }
                (artifact_root / f"{slug}-geometry.json").write_text(
                    json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                assert measurements["viewport"] == {"width": 1240, "height": 1754}
                assert measurements["cardCount"] == count
                for safety_check in (
                    "cardsInside",
                    "gridInside",
                    "footerAfterGrid",
                    "noCardOverflow",
                    "noStageTextCollision",
                    "badgesInside",
                    "pricesInside",
                    "titlesClamped",
                    "imagesLoaded",
                    "imagesContained",
                    "cardTopBordersReduced",
                    "noCardCollisions",
                ):
                    assert measurements[safety_check], safety_check
                assert not page_errors and not console_errors and not failed_requests
                assert measurements["fallbackCount"] == 1
                assert measurements["densityProfile"] == reference["density"]
                assert measurements["featuredCount"] == reference["featured"]
                assert measurements["cutoutStageCount"] == {4: 3, 9: 6, 16: 12}[count]
                assert measurements["heavyBorderSideCount"] == 0
                assert measurements["cardWidthTiers"] >= reference["min_width_tiers"]
                assert measurements["stageHeightRange"] >= reference["min_stage_delta"]
                assert min(measurements["priceWidthRatios"]) >= reference["min_price_ratio"]
                assert max(measurements["priceWidthRatios"]) <= 0.98
                assert (
                    max(measurements["priceWidthRatios"]) - min(measurements["priceWidthRatios"])
                    >= reference["min_price_width_delta"]
                )
                assert measurements["pricePatternCount"] >= reference["min_price_patterns"]
                assert measurements["fullSeparatorCount"] == 0
                assert measurements["enclosingBorderCount"] == 0
                if count == 4:
                    assert measurements["secondaryEnclosingBorderCount"] == 0
                    assert measurements["compositionGroups"] == 2
                    assert (
                        measurements["featuredStageHeightRatio"]
                        >= reference["min_featured_stage_height_ratio"]
                    )
                    assert (
                        measurements["supportStageHeightRange"]
                        <= reference["max_support_stage_height_range"]
                    )
                elif count == 9:
                    assert measurements["imageStageHeightTiers"] >= reference["min_stage_tiers"]
                    assert measurements["sharedSectionSurface"]
                    assert measurements["imageTopTiers"] >= 3
                    assert (
                        measurements["priceTreatmentCount"]
                        >= reference["min_visual_price_treatments"]
                    )
                    assert (
                        measurements["priceTreatmentGeometryCount"]
                        >= reference["min_visual_price_treatments"]
                    )
                    assert (
                        measurements["perceptibleVerticalOffsetCount"]
                        >= reference["min_perceptible_offsets"]
                    )
                    assert all(
                        image_range >= 12 or price_range >= 12
                        for image_range, price_range in zip(
                            measurements["logicalRowImageTopRanges"],
                            measurements["logicalRowPriceTopRanges"],
                            strict=True,
                        )
                    )
                    assert measurements["lowerOpaqueCardCount"] == 0
                    assert measurements["lowerCardWidthTiers"] >= reference["min_lower_width_tiers"]
                    assert measurements["compositionGroups"] == 3
                else:
                    assert measurements["sharedSectionSurface"]
                    assert measurements["imageStageHeightTiers"] >= reference["min_stage_tiers"]
                    assert measurements["imageTierCount"] >= 3
                    assert (
                        measurements["priceTreatmentCount"]
                        >= reference["min_visual_price_treatments"]
                    )
                    assert (
                        measurements["priceTreatmentGeometryCount"]
                        >= reference["min_visual_price_treatments"]
                    )
                    assert (
                        measurements["perceptibleVerticalOffsetCount"]
                        >= reference["min_perceptible_offsets"]
                    )
                    assert all(value >= 12 for value in measurements["logicalRowPriceTopRanges"])
                    assert measurements["opaqueCardCount"] == 0
                    assert measurements["compositionGroups"] == 4
                if reference["featured"]:
                    assert measurements["featuredAreaRatio"] >= reference["min_featured_area_ratio"]
                    assert (
                        measurements["featuredImageRatio"] >= reference["min_featured_image_ratio"]
                    )
                    assert (
                        measurements["featuredPriceRatio"] >= reference["min_featured_price_ratio"]
                    )
                page.screenshot(
                    path=str(png_path), clip={"x": 0, "y": 0, "width": 1240, "height": 1754}
                )
                page.screenshot(
                    path=str(second_png_path), clip={"x": 0, "y": 0, "width": 1240, "height": 1754}
                )
                page.pdf(path=str(pdf_path), format="A4", print_background=True, scale=0.635)
            finally:
                browser.close()
    except ImportError as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with (
        Image.open(png_path).convert("RGBA") as first,
        Image.open(second_png_path).convert("RGBA") as second,
    ):
        assert ImageChops.difference(first, second).getbbox() is None
    render_html_to_png_sync(html, export_png_path)
    render_html_to_png_sync(html, repeat_export_png_path)
    render_html_to_pdf_sync(html, export_pdf_path)

    with Image.open(png_path) as png:
        assert png.size == (2480, 3508)
    pdf = PdfReader(str(pdf_path))
    with (
        Image.open(png_path).convert("RGBA") as preview_png,
        Image.open(export_png_path).convert("RGBA") as export_png,
    ):
        assert ImageChops.difference(preview_png, export_png).getbbox() is None
    assert export_png_path.read_bytes() == repeat_export_png_path.read_bytes()

    assert len(pdf.pages) == 1
    assert abs(float(pdf.pages[0].mediabox.width) - 595.276) < 2
    assert abs(float(pdf.pages[0].mediabox.height) - 841.89) < 2
    export_pdf = PdfReader(str(export_pdf_path))
    assert len(export_pdf.pages) == 1
    assert abs(float(export_pdf.pages[0].mediabox.width) - 595.276) < 2
    assert abs(float(export_pdf.pages[0].mediabox.height) - 841.89) < 2


@pytest.mark.parametrize(
    ("count", "strategy"),
    [(1, "single-poster"), (2, "split-pair"), (3, "balanced-trio")],
)
def test_real_chromium_small_campaign_layouts_fill_the_page_without_collisions(
    count: int, strategy: str
) -> None:
    items = [
        {
            "id": str(index),
            "name": f"Small campaign product {index + 1}",
            "price": f"{index + 1}.99",
            "old_price": f"{index + 2}.49",
            "currency": "EUR",
            "badge": "SPECIAL",
        }
        for index in range(count)
    ]
    payload = {
        "template_slug": "supermarket-promo-4",
        "market_name": "Fixture Market",
        "title": "Small campaign offers",
        "builder_config": {"smart_composition": True},
        "items": items,
    }
    html = render_render_payload_html(payload, generated_at=FIXED_TIME)
    assert f'data-refinement-strategy="{strategy}"' in html

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except PlaywrightError as exc:
                pytest.skip(f"Playwright Chromium unavailable: {exc}")
            try:
                page = browser.new_page(viewport={"width": 1240, "height": 1754})
                page.set_content(html, wait_until="networkidle")
                measurements = page.evaluate(
                    """() => {
                      const rect = (element) => {
                        const value = element.getBoundingClientRect();
                        return {left: value.left, top: value.top, right: value.right, bottom: value.bottom};
                      };
                      const area = (box) => (box.right - box.left) * (box.bottom - box.top);
                      const overlaps = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
                      const documentBox = rect(document.querySelector('.preview-document'));
                      const gridBox = rect(document.querySelector('.product-grid'));
                      const cards = [...document.querySelectorAll('.product-card')];
                      const cardBoxes = cards.map(rect);
                      return {
                        viewport: {width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight},
                        cardsInside: cardBoxes.every((box) => box.left >= documentBox.left && box.top >= documentBox.top && box.right <= documentBox.right && box.bottom <= documentBox.bottom),
                        noOverflow: cards.every((card) => card.scrollWidth <= card.clientWidth && card.scrollHeight <= card.clientHeight),
                        noCollisions: cardBoxes.every((box, index) => cardBoxes.slice(index + 1).every((other) => !overlaps(box, other))),
                        usedAreaRatio: cardBoxes.reduce((total, box) => total + area(box), 0) / area(gridBox),
                        reachesPageBottom: Math.max(...cardBoxes.map((box) => box.bottom)) >= gridBox.top + (gridBox.bottom - gridBox.top) * .88,
                        fallbackCount: document.querySelectorAll('.image-placeholder').length,
                      };
                    }"""
                )
            finally:
                browser.close()
    except ImportError as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    assert measurements["viewport"] == {"width": 1240, "height": 1754}
    assert measurements["cardsInside"]
    assert measurements["noOverflow"]
    assert measurements["noCollisions"]
    assert measurements["usedAreaRatio"] >= 0.68
    assert measurements["reachesPageBottom"]
    assert measurements["fallbackCount"] == count


# --- Phase 28B acceptance fixtures ---------------------------------------
# Same 3-product campaign as the task spec's Case 1/2/3, run through the real
# visual quality gate (run_visual_quality_gate) with real Chromium - not just
# render_render_payload_html - to prove the CSS fix (preview_renderer.py's
# now-deleted "simplified-grid" branch) actually resolves the sparse
# 3-product-simple layout, and that the gate behaves as designed end to end.

def _three_product_payload(*, hero: bool = False, hero_id: str = "1", visual_density: str | None = None) -> dict:
    """Build the fixed 3-product fixture; `hero_id` picks which item (by DOM/
    campaign position - "1"=Coca Cola, "2"=Eti Burcak, "3"=Sutas Yogurt) carries
    is_hero, so tests can prove hero dominance is independent of DOM order.
    """
    items = [
        {"id": "1", "name": "Coca Cola 1L", "price": "29.90", "currency": "TRY", "is_hero": hero and hero_id == "1"},
        {"id": "2", "name": "Eti Burcak", "price": "44.90", "currency": "TRY", "is_hero": hero and hero_id == "2"},
        {"id": "3", "name": "Sutas Yogurt", "price": "74.90", "currency": "TRY", "is_hero": hero and hero_id == "3"},
    ]
    return {
        "template_slug": "supermarket-promo-4",
        "market_name": "Fixture Market",
        "title": "Haftanin Firsatlari",
        "builder_config": {"visual_density": visual_density} if visual_density else {},
        "items": items,
    }


def _run_gate_or_skip(payload: dict):
    try:
        from playwright.sync_api import Error as PlaywrightError
    except ImportError as exc:
        pytest.skip(f"Playwright unavailable: {exc}")
    try:
        return run_visual_quality_gate(
            payload,
            generated_at=FIXED_TIME,
            market_id=uuid4(),
            campaign_id=uuid4(),
            export_job_id=uuid4(),
        )
    except PlaywrightError as exc:
        pytest.skip(f"Playwright Chromium unavailable: {exc}")


def _measure_page_fill(html: str) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1240, "height": 1754})
            page.set_content(html, wait_until="networkidle")
            return page.evaluate(
                """() => {
                  const rect = (element) => { const value = element.getBoundingClientRect(); return {left: value.left, top: value.top, right: value.right, bottom: value.bottom}; };
                  const area = (box) => (box.right - box.left) * (box.bottom - box.top);
                  const gridBox = rect(document.querySelector('.product-grid'));
                  const cardBoxes = [...document.querySelectorAll('.product-card')].map(rect);
                  return {
                    usedAreaRatio: cardBoxes.reduce((total, box) => total + area(box), 0) / area(gridBox),
                    reachesPageBottom: Math.max(...cardBoxes.map((box) => box.bottom)) >= gridBox.top + (gridBox.bottom - gridBox.top) * .88,
                  };
                }"""
            )
        finally:
            browser.close()


def _measure_text_contrast(html: str) -> list[float]:
    """Per-card WCAG contrast ratio between .product-name's painted color and

    a guaranteed-empty background sample from its own card (top-left padding
    corner, before any content starts) - Phase 31 regression coverage for the
    white-on-cream text bug (composition-hero-offers' hero-card text color
    leaking into the small-layout-* geometry, see preview_renderer.py).
    """
    from playwright.sync_api import sync_playwright

    from app.services.template_presets import contrast_ratio

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1240, "height": 1754})
            page.set_content(html, wait_until="networkidle")
            samples = page.evaluate(
                """() => {
                  const toHex = (rgbString) => {
                    const parts = rgbString.match(/\\d+/g).map(Number);
                    return '#' + parts.slice(0, 3).map((c) => c.toString(16).padStart(2, '0')).join('');
                  };
                  return [...document.querySelectorAll('.product-card')].map((card) => {
                    const name = card.querySelector('.product-name');
                    const cardBox = card.getBoundingClientRect();
                    return {
                      textColor: name ? toHex(getComputedStyle(name).color) : null,
                      sampleX: Math.round(cardBox.left + 8),
                      sampleY: Math.round(cardBox.top + 8),
                    };
                  });
                }"""
            )
            screenshot = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
            ratios = []
            for sample in samples:
                if sample["textColor"] is None:
                    continue
                bg_rgb = screenshot.getpixel((sample["sampleX"], sample["sampleY"]))
                bg_hex = "#" + "".join(f"{channel:02x}" for channel in bg_rgb)
                ratios.append(contrast_ratio(bg_hex, sample["textColor"]))
            return ratios
        finally:
            browser.close()


def _extract_product_names(html: str) -> list[str]:
    return re.findall(r'<h2 class="product-name"[^>]*>([^<]*)</h2>', html)


def _extract_price_majors(html: str) -> list[str]:
    return re.findall(r'<span class="price-major">([^<]*)</span>', html)


def _write_case_report(artifact_root: Path, name: str, payload: dict, result) -> None:
    artifact_root.mkdir(parents=True, exist_ok=True)
    report = {
        "case": name,
        "initial_score": result.initial_score.overall_score if result.initial_score else None,
        "issues": list(result.initial_score.issues) if result.initial_score else [],
        "refinement_triggered": result.refinement_action is not None,
        "refinement_action": result.refinement_action,
        "refined_score": result.refined_score.overall_score if result.refined_score else None,
        "selected_result": "refined" if result.applied else "initial",
    }
    (artifact_root / f"quality-gate-{name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def test_quality_gate_case1_balanced_three_products_meets_threshold(tmp_path: Path) -> None:
    payload = _three_product_payload()
    result = _run_gate_or_skip(payload)
    assert result.initial_score is not None
    assert result.initial_score.overflow_ok
    assert result.initial_score.collision_ok
    assert result.initial_score.overall_score >= QUALITY_THRESHOLD
    assert result.applied is False
    assert 'data-refinement-strategy="balanced-trio"' in result.html

    # Phase 31: default must use substantially more of the page - a severe
    # page-fill/content-fill failure must not hide behind a passing weighted score.
    assert result.initial_score.content_fill_score >= 60.0
    assert "content_fill_low" not in result.initial_score.issues
    measurements = _measure_page_fill(result.html)
    assert measurements["usedAreaRatio"] >= 0.68
    assert measurements["reachesPageBottom"]

    # Phase 31: product names must stay readable against their real background,
    # not white-on-cream (composition-hero-offers text color leaking into
    # balanced-trio's light card surface).
    contrasts = _measure_text_contrast(result.html)
    assert len(contrasts) == 3
    assert all(ratio >= 4.5 for ratio in contrasts)

    _write_case_report(Path(os.environ.get("FLYER_VISUAL_ARTIFACT_DIR", tmp_path / "artifacts")), "case1", payload, result)


def test_quality_gate_case2_hero_product_is_measurably_dominant(tmp_path: Path) -> None:
    payload = _three_product_payload(hero=True)
    result = _run_gate_or_skip(payload)
    assert result.initial_score is not None
    assert result.initial_score.overflow_ok
    assert result.initial_score.collision_ok
    assert result.initial_score.hero_dominance_applicable
    assert result.initial_score.hero_dominance_score >= 65.0
    assert 'data-refinement-strategy="hero-trio"' in result.html
    # Hero targeting is untouched by the gate - same item, same flag, no reorder.
    assert payload["items"][0]["id"] == "1"
    assert payload["items"][0]["is_hero"] is True

    # Phase 31: hero must dominate without leaving giant purposeless blank regions.
    assert result.initial_score.content_fill_score >= 60.0
    assert "content_fill_low" not in result.initial_score.issues
    measurements = _measure_page_fill(result.html)
    assert measurements["usedAreaRatio"] >= 0.68
    assert measurements["reachesPageBottom"]

    # Phase 31: hero and support product names must both stay readable.
    contrasts = _measure_text_contrast(result.html)
    assert len(contrasts) == 3
    assert all(ratio >= 4.5 for ratio in contrasts)

    _write_case_report(Path(os.environ.get("FLYER_VISUAL_ARTIFACT_DIR", tmp_path / "artifacts")), "case2", payload, result)


def test_quality_gate_case3_simple_mode_produces_intentional_composition_not_legacy_grid(tmp_path: Path) -> None:
    """Regression test for the preview_renderer.py "simplified-grid" bug (Phase 28B section 1).

    Before the fix this would render a CSS-less "simplified-grid" layout
    (undersized cards in a 2x2 grid with one empty cell) instead of the
    full-bleed balanced-trio geometry.
    """
    payload = _three_product_payload(visual_density="simple")
    result = _run_gate_or_skip(payload)
    assert result.initial_score is not None
    assert result.initial_score.overflow_ok
    assert result.initial_score.collision_ok
    assert 'data-refinement-strategy="balanced-trio"' in result.html
    assert "small-layout-simplified-grid" not in result.html
    assert "composition-simplified-grid" not in result.html

    measurements = _measure_page_fill(result.html)
    assert measurements["usedAreaRatio"] >= 0.68
    assert measurements["reachesPageBottom"]
    assert result.initial_score.content_fill_score >= 60.0
    assert "content_fill_low" not in result.initial_score.issues
    # The CSS fix alone should already clear the quality threshold - the gate
    # is a safety net here, not the primary fix.
    assert result.initial_score.overall_score >= QUALITY_THRESHOLD
    assert result.applied is False

    contrasts = _measure_text_contrast(result.html)
    assert len(contrasts) == 3
    assert all(ratio >= 4.5 for ratio in contrasts)

    _write_case_report(Path(os.environ.get("FLYER_VISUAL_ARTIFACT_DIR", tmp_path / "artifacts")), "case3", payload, result)


# --- Phase 31 follow-up hotfix: hero-trio must follow is_hero, not DOM order ---
# Before this fix, small-layout-hero-trio sized its "big" card with a bare
# `:first-child` CSS selector. is_hero never reordered the underlying item
# list (that reorder only ever fires for `emphasis=="featured"`, a separate
# field the raw render payload here never sets), so a hero that wasn't
# already the first product would size the wrong card. The fixture above
# only ever put the hero (Coca Cola) first, which masked the bug - these
# cases put the hero second and third instead.

def _measure_card_geometry_by_name(html: str) -> dict[str, dict]:
    """Real-Chromium per-card geometry keyed by product name - proves which

    card is actually rendered large, not just which CSS class/attribute is
    present in the markup.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1240, "height": 1754})
            page.set_content(html, wait_until="networkidle")
            return {
                entry["name"]: entry
                for entry in page.evaluate(
                    """() => [...document.querySelectorAll('.product-card')].map((card) => {
                      const box = card.getBoundingClientRect();
                      const price = card.querySelector('.price');
                      return {
                        name: card.querySelector('.product-name')?.textContent ?? '',
                        hero: card.dataset.hero,
                        area: Math.max(0, box.right - box.left) * Math.max(0, box.bottom - box.top),
                        priceFontSize: price ? parseFloat(getComputedStyle(price).fontSize) : 0,
                      };
                    })"""
                )
            }
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("hero_id", "hero_name", "other_names"),
    [
        ("3", "Sutas Yogurt", ("Coca Cola 1L", "Eti Burcak")),  # Case 1: last item is hero
        ("2", "Eti Burcak", ("Coca Cola 1L", "Sutas Yogurt")),  # Case 2: middle item is hero
    ],
)
def test_hero_trio_dominance_follows_is_hero_not_dom_position(hero_id, hero_name, other_names) -> None:
    payload = _three_product_payload(hero=True, hero_id=hero_id)
    html = render_render_payload_html(payload, generated_at=FIXED_TIME)

    # Facts and DOM/campaign order are untouched by hero selection - only the
    # semantic data-hero marker on the actual hero product changes.
    assert _extract_product_names(html) == ["Coca Cola 1L", "Eti Burcak", "Sutas Yogurt"]
    assert _extract_price_majors(html) == ["29", "44", "74"]
    assert 'data-refinement-strategy="hero-trio"' in html

    try:
        geometry = _measure_card_geometry_by_name(html)
    except Exception as exc:  # pragma: no cover - environment guard
        from playwright.sync_api import Error as PlaywrightError

        if isinstance(exc, (ImportError, PlaywrightError)):
            pytest.skip(f"Playwright Chromium unavailable: {exc}")
        raise

    hero_card = geometry[hero_name]
    assert hero_card["hero"] == "true"
    for other_name in other_names:
        other_card = geometry[other_name]
        assert other_card["hero"] == "false"
        # The hero card must be measurably dominant in both card area and
        # price font size - not merely tagged with the right CSS class.
        assert hero_card["area"] > other_card["area"] * 1.5
        assert hero_card["priceFontSize"] > other_card["priceFontSize"]


def test_hero_trio_simple_mode_flattens_dominance_but_keeps_is_hero_fact() -> None:
    """Case 4: simple mode after a non-first hero selection must flatten

    visual dominance (balanced-trio, not hero-trio) while leaving the
    campaign's is_hero fact - and product order/prices - untouched.
    """
    payload = _three_product_payload(hero=True, hero_id="3", visual_density="simple")
    html = render_render_payload_html(payload, generated_at=FIXED_TIME)

    assert payload["items"][2]["is_hero"] is True
    assert _extract_product_names(html) == ["Coca Cola 1L", "Eti Burcak", "Sutas Yogurt"]
    assert _extract_price_majors(html) == ["29", "44", "74"]
    assert 'data-refinement-strategy="balanced-trio"' in html
    # SUPERMARKET_ART_DIRECTION_CSS always ships the hero-trio ruleset (it's a
    # static stylesheet, not conditionally emitted), so check the actually
    # applied class token on <main>, not mere substring presence in the CSS.
    assert not re.search(r'<main class="[^"]*\bsmall-layout-hero-trio\b', html)
    # The internal is_hero semantic is still rendered on the card (marker is
    # layout-agnostic) - simple mode only stops hero-trio geometry from
    # consuming it.
    assert re.search(r'<article class="product-card"[^>]*\bdata-hero="true"', html)


def test_balanced_trio_default_behavior_unchanged_without_hero() -> None:
    """Case 5: no explicit hero keeps the existing balanced-trio behavior."""
    payload = _three_product_payload()
    html = render_render_payload_html(payload, generated_at=FIXED_TIME)

    assert 'data-refinement-strategy="balanced-trio"' in html
    # SUPERMARKET_ART_DIRECTION_CSS always ships the hero-trio ruleset (it's a
    # static stylesheet, not conditionally emitted), so check the actually
    # applied class token on <main>, not mere substring presence in the CSS.
    assert not re.search(r'<main class="[^"]*\bsmall-layout-hero-trio\b', html)
    assert not re.search(r'<article class="product-card"[^>]*\bdata-hero="true"', html)
    assert _extract_product_names(html) == ["Coca Cola 1L", "Eti Burcak", "Sutas Yogurt"]


def test_quality_gate_hero_dominance_score_tracks_non_first_hero(tmp_path: Path) -> None:
    """Real-Chromium quality-gate coverage (not just render_render_payload_html)

    for a non-first hero, mirroring case2's gate assertions but with the hero
    on the last product - proves the gate's own hero-dominance metric (which
    reads a different data attribute set than the CSS) also identifies the
    correct card after this fix.
    """
    payload = _three_product_payload(hero=True, hero_id="3")
    result = _run_gate_or_skip(payload)
    assert result.initial_score is not None
    assert result.initial_score.overflow_ok
    assert result.initial_score.collision_ok
    assert result.initial_score.hero_dominance_applicable
    assert result.initial_score.hero_dominance_score >= 65.0
    assert 'data-refinement-strategy="hero-trio"' in result.html
    assert payload["items"][2]["id"] == "3"
    assert payload["items"][2]["is_hero"] is True
    assert _extract_product_names(result.html) == ["Coca Cola 1L", "Eti Burcak", "Sutas Yogurt"]

    _write_case_report(Path(os.environ.get("FLYER_VISUAL_ARTIFACT_DIR", tmp_path / "artifacts")), "case1-non-first-hero", payload, result)


def test_phase31_facts_and_image_association_preserved_across_default_hero_simple() -> None:
    """Conversational edits (hero, then "daha sade yap") must reuse the same

    campaign facts: identical prices/names/order, and the same safe
    "no usable image" fallback for every item (Phase 31 Gap A - none of the
    fixture products have catalog images, so all three must stay on the
    documented safe fallback in every mode, never a fabricated/mismatched image).
    """
    default_html = render_render_payload_html(_three_product_payload(), generated_at=FIXED_TIME)
    hero_html = render_render_payload_html(_three_product_payload(hero=True), generated_at=FIXED_TIME)
    simple_html = render_render_payload_html(_three_product_payload(visual_density="simple"), generated_at=FIXED_TIME)

    expected_names = ["Coca Cola 1L", "Eti Burcak", "Sutas Yogurt"]
    expected_prices = ["29", "44", "74"]
    for html in (default_html, hero_html, simple_html):
        assert _extract_product_names(html) == expected_names
        assert _extract_price_majors(html) == expected_prices
        # Match only the rendered element's attribute, not the (also-present)
        # image-coverage-image-poor CSS selector of the same name.
        assert len(re.findall(r'<div class="promo-card-image" data-image-stage="fallback">', html)) == 3
        assert html.count('<div class="image-placeholder">') == 3
