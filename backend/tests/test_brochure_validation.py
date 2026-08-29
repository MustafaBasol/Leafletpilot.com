import sys
from io import BytesIO
from types import SimpleNamespace

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
    assert "current_price" in result.report["critical_facts"]["missing_categories"]


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
