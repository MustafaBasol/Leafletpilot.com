from decimal import Decimal

import pytest
from app.services.product_normalization import format_package, normalize_currency, normalize_package_type, normalized_package_values, parse_package


@pytest.mark.parametrize(("source", "amount", "unit"), [("100gr", "100", "g"), ("100 grammes", "100", "g"), ("1 kilo", "1", "kg"), ("500 millilitres", "500", "ml"), ("33cl", "33", "cl"), ("1lt", "1", "l"), ("6 adet", "6", "pcs"), ("6 pièces", "6", "pcs"), ("1,5 L", "1.5", "l")])
def test_package_parser_canonicalizes_supported_turkish_and_french_values(source, amount, unit):
    assert parse_package(source) == (Decimal(amount), unit)


def test_package_contract_is_canonical_and_compatible():
    values = normalized_package_values({"package_size": "500 g", "package_type": "BOX", "currency": "chf"})
    assert values == {**values, "package_size": "500 g", "package_amount": Decimal("500"), "package_unit": "g", "package_type_canonical": "box", "currency": "CHF"}
    assert format_package(Decimal("1.5"), "l") == "1.5 l"
    assert parse_package("Aile Boyu") == (None, None)
    assert normalize_package_type("şişe") == "bottle"
    assert normalize_currency("unknown") == "EUR"
    with pytest.raises(ValueError): normalize_currency("unknown", strict=True)


def test_partial_normalization_does_not_add_or_erase_omitted_values():
    assert normalized_package_values({"package_size": "Aile Boyu"}) == {"package_size": "Aile Boyu"}
    assert normalized_package_values({"package_amount": Decimal("100"), "package_unit": "g"})["package_size"] == "100 g"
    assert normalized_package_values({"package_amount": None}) == {"package_amount": None}
