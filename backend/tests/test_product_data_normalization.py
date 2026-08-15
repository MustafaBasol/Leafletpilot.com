from decimal import Decimal

from app.services.product_normalization import format_package, normalize_currency, normalize_package_type, normalized_package_values, parse_package


def test_turkish_package_parser_and_legacy_formatter_are_compatible():
    amount, unit = parse_package("1,5 L")
    assert (amount, unit) == (Decimal("1.5"), "L")
    assert format_package(amount, unit) == "1.5 L"
    assert format_package(Decimal("500"), "g") == "500 g"
    assert format_package(None, None, "eski değer") == "eski değer"


def test_canonical_product_values_keep_display_input_and_normalize_known_values():
    values = normalized_package_values({"package_size": "500 g", "package_type": "BOX", "currency": "try"})
    assert values["package_size"] == "500 g"
    assert values["package_amount"] == Decimal("500")
    assert values["package_unit"] == "g"
    assert values["package_type_canonical"] == "kutu"
    assert values["currency"] == "TRY"
    assert normalize_currency("unknown") == "EUR"
    assert normalize_package_type("Bottle") == "şişe"
