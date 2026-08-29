import sys
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from app.services.ai.brochure_validation import validate_generated_brochure


def candidate_png() -> bytes:
    image = Image.new("RGB", (1024, 1536), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1024, 240), fill="navy")
    draw.rectangle((80, 340, 944, 1420), outline="red", width=12)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def ocr_text_png() -> bytes:
    image = Image.new("RGB", (1024, 1536), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 120), "Vatan Market", fill="black")
    draw.text((80, 240), "Hafta Fırsatları", fill="black")
    draw.text((80, 360), "Coca Cola 1,99", fill="black")
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()

def snapshot() -> dict:
    return {
        "market_name": "Vatan Market",
        "title": "Hafta Fırsatları",
        "header": {},
        "items": [{"name": "Coca Cola", "price": "1,99"}],
    }


def install_ocr(monkeypatch, responses):
    remaining = list(responses)

    def image_to_data(*_args, **_kwargs):
        response = remaining.pop(0) if remaining else responses[-1]
        if isinstance(response, Exception):
            raise response
        text, confidence = response
        words = text.split()
        return {"text": words, "conf": [str(confidence)] * len(words)}

    fake = SimpleNamespace(Output=SimpleNamespace(DICT="dict"), image_to_data=image_to_data)
    monkeypatch.setitem(sys.modules, "pytesseract", fake)


def test_valid_candidate_is_verified_after_layered_validation(monkeypatch) -> None:
    install_ocr(monkeypatch, [("Vatan Market Hafta Fırsatları Coca Cola 1,99", 92)])

    result = validate_generated_brochure(candidate_png(), snapshot(), logo_required=False)

    assert result.accepted is True
    assert result.report["evidence_status"] == "verified"
    assert len(result.report["ocr"]["passes"]) >= 3


def test_low_ocr_confidence_is_unverifiable_not_mismatch(monkeypatch) -> None:
    install_ocr(monkeypatch, [("Vatan Market Hafta Fırsatları Coca Cola 1,99", 22)])

    result = validate_generated_brochure(candidate_png(), snapshot(), logo_required=False)

    assert result.accepted is False
    assert result.report["evidence_status"] == "unverifiable"
    assert result.report["reason"] == "ocr_low_confidence"


def test_confirmed_commercial_mismatch_is_distinct(monkeypatch) -> None:
    install_ocr(monkeypatch, [("Vatan Market Hafta Fırsatları Coca Cola 9,99", 94)])

    result = validate_generated_brochure(candidate_png(), snapshot(), logo_required=False)

    assert result.accepted is False
    assert result.report["evidence_status"] == "mismatch"
    assert result.report["reason"] == "commercial_fact_mismatch"
    assert "current_price" in result.report["critical_facts"]["conflicting_categories"]


def test_secondary_preprocessing_pass_can_verify_a_candidate(monkeypatch) -> None:
    install_ocr(
        monkeypatch,
        [
            ("unreadable", 18),
            ("Vatan Market Hafta Fırsatları Coca Cola 1,99", 91),
        ],
    )

    result = validate_generated_brochure(candidate_png(), snapshot(), logo_required=False)

    assert result.accepted is True
    assert result.report["ocr"]["passes"][0]["matched_fact_count"] == 0
    assert result.report["ocr"]["passes"][1]["matched_fact_count"] == 4


def test_genuinely_unavailable_ocr_still_fails_closed(monkeypatch) -> None:
    install_ocr(monkeypatch, [RuntimeError("tesseract unavailable")])

    result = validate_generated_brochure(candidate_png(), snapshot(), logo_required=False)

    assert result.accepted is False
    assert result.report["evidence_status"] == "unverifiable"
    assert result.report["reason"] == "ocr_unavailable"


def test_pytesseract_import_is_available() -> None:
    pytesseract = pytest.importorskip("pytesseract")

    assert pytesseract.image_to_data


def test_installed_pytesseract_executes_ocr_path() -> None:
    pytesseract = pytest.importorskip("pytesseract")
    try:
        pytesseract.get_tesseract_version()
    except (pytesseract.TesseractNotFoundError, OSError):
        pytest.skip("tesseract executable is not installed in this test environment")

    result = validate_generated_brochure(ocr_text_png(), snapshot(), logo_required=False)

    assert result.report["ocr"]["available"] is True
    assert result.report["ocr"]["passes"]

def brochure_snapshot(*, name="Coca Cola", price="1,46", old_price=None, title="Weekly Deals"):
    item = {"name": name, "price": price}
    if old_price is not None:
        item["old_price"] = old_price
    return {
        "market_name": "Vatan Market",
        "title": title,
        "header": {},
        "items": [item],
    }


def run_brochure_ocr(monkeypatch, snapshot_value, text):
    install_ocr(monkeypatch, [(text, 94)])
    return validate_generated_brochure(
        candidate_png(), snapshot_value, logo_required=False
    )


@pytest.mark.parametrize("ocr_price", ["1.46", "1,46", "1 46", "�1,46", "1,46�"])
def test_equivalent_price_renderings_are_verified(monkeypatch, ocr_price) -> None:
    result = run_brochure_ocr(
        monkeypatch,
        brochure_snapshot(),
        f"Vatan Market Weekly Deals Coca Cola {ocr_price}",
    )

    assert result.accepted is True


def test_collapsed_three_digit_price_without_decimal_context_is_unverifiable(monkeypatch):
    result = run_brochure_ocr(
        monkeypatch,
        brochure_snapshot(),
        "Vatan Market Weekly Deals Coca Cola 146",
    )

    assert result.report["evidence_status"] == "unverifiable"
    assert result.report["reason"] == "critical_facts_unverifiable"
    assert result.report["critical_facts"]["conflicting_count"] == 0


def test_confidently_different_price_is_a_mismatch(monkeypatch) -> None:
    result = run_brochure_ocr(
        monkeypatch,
        brochure_snapshot(),
        "Vatan Market Weekly Deals Coca Cola 1,96",
    )

    assert result.report["evidence_status"] == "mismatch"
    assert result.report["reason"] == "commercial_fact_mismatch"
    assert result.report["critical_facts"]["conflicting_count"] == 1


def test_missing_price_is_unverifiable_not_a_mismatch(monkeypatch) -> None:
    result = run_brochure_ocr(
        monkeypatch,
        brochure_snapshot(),
        "Vatan Market Weekly Deals Coca Cola",
    )

    assert result.report["evidence_status"] == "unverifiable"
    assert result.report["critical_facts"]["conflicting_count"] == 0



def test_product_accent_degradation_matches(monkeypatch) -> None:
    result = run_brochure_ocr(
        monkeypatch,
        brochure_snapshot(name="Caf" + chr(233) + " Cr" + chr(232) + "me"),
        "Vatan Market Weekly Deals Cafe Creme 1,46",
    )

    assert result.accepted is True


def test_partial_discriminative_product_tokens_match(monkeypatch) -> None:
    result = run_brochure_ocr(
        monkeypatch,
        brochure_snapshot(name="Coca Cola Classic"),
        "Vatan Market Weekly Deals Coca Classic 1,46",
    )

    assert result.accepted is True


def test_clearly_different_product_is_a_mismatch(monkeypatch) -> None:
    result = run_brochure_ocr(
        monkeypatch,
        brochure_snapshot(),
        "Vatan Market Weekly Deals Pepsi Cola 1,46",
    )

    assert result.report["evidence_status"] == "mismatch"
    assert result.report["reason"] == "commercial_fact_mismatch"
    assert "product_name" in result.report["critical_facts"]["conflicting_categories"]


def test_missing_product_is_unverifiable(monkeypatch) -> None:
    result = run_brochure_ocr(
        monkeypatch,
        brochure_snapshot(),
        "Vatan Market Weekly Deals 1,46",
    )

    assert result.report["evidence_status"] == "unverifiable"
    assert result.report["critical_facts"]["conflicting_count"] == 0


def test_missing_campaign_title_alone_is_unverifiable(monkeypatch) -> None:
    result = run_brochure_ocr(
        monkeypatch,
        brochure_snapshot(),
        "Vatan Market Coca Cola 1,46",
    )

    assert result.report["evidence_status"] == "unverifiable"
    assert result.report["reason"] == "critical_facts_unverifiable"
    assert result.report["critical_facts"]["missing_categories"] == ["campaign_title"]


def test_insufficient_product_identities_make_order_unverifiable(monkeypatch) -> None:
    snapshot_value = {
        "market_name": "Vatan Market",
        "title": "Weekly Deals",
        "header": {},
        "items": [
            {"name": "Coca Cola", "price": "1,46"},
            {"name": "Pepsi Max", "price": "2,46"},
        ],
    }
    result = run_brochure_ocr(
        monkeypatch,
        snapshot_value,
        "Vatan Market Weekly Deals Coca Cola 1,46",
    )

    assert result.report["critical_facts"]["product_order"] is None
    assert result.report["evidence_status"] == "unverifiable"


def test_confidently_wrong_product_order_is_a_mismatch(monkeypatch) -> None:
    snapshot_value = {
        "market_name": "Vatan Market",
        "title": "Weekly Deals",
        "header": {},
        "items": [
            {"name": "Coca Cola", "price": "1,46"},
            {"name": "Pepsi Max", "price": "2,46"},
        ],
    }
    result = run_brochure_ocr(
        monkeypatch,
        snapshot_value,
        "Vatan Market Weekly Deals Pepsi Max 2,46 Coca Cola 1,46",
    )

    assert result.report["critical_facts"]["product_order"] is False
    assert result.report["evidence_status"] == "mismatch"


def test_production_pattern_with_unreadable_facts_is_not_a_mismatch(monkeypatch):
    names = [
        "Alpha Goods",
        "Bravo Goods",
        "Charlie Goods",
        "Delta Goods",
        "Echo Goods",
        "Foxtrot Goods",
        "Golf Goods",
        "Hotel Goods",
        "India Goods",
        "Juliet Goods",
    ]
    snapshot_value = {
        "market_name": "Vatan Market",
        "title": "Weekly Deals",
        "market_profile": {
            "visibility": {"address": True, "phone": True},
            "address": "Main Street 1",
            "phone": "+49 111",
        },
        "header": {"validity_text": "01-07", "footer_note": "Limited stock"},
        "items": [
            {"name": name, "price": f"{index + 1},46", "old_price": f"{index + 2},46"}
            for index, name in enumerate(names)
        ],
    }
    visible = " ".join(
        [
            "Vatan Market Main Street 1 +49 111 01-07 Limited stock",
            *[
                f"{name} {index + 1},46 {index + 2},46"
                for index, name in enumerate(names[:6])
            ],
            names[6],
        ]
    )
    result = run_brochure_ocr(monkeypatch, snapshot_value, visible)

    facts = result.report["critical_facts"]
    assert facts["required_count"] == 36
    assert facts["matched_count"] == 24
    assert facts["unreadable_count"] == 12
    assert facts["conflicting_count"] == 0
    assert facts["product_order"] is None
    assert result.report["evidence_status"] == "unverifiable"
    assert result.report["reason"] == "critical_facts_unverifiable"
