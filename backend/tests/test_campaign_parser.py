from decimal import Decimal

from app.services.campaign_parser import clean_product_name, parse_campaign_text, parse_price


def test_empty_input_returns_no_items() -> None:
    assert parse_campaign_text("\n\n") == []


def test_simple_dash_price() -> None:
    item = parse_campaign_text("Coca Cola 2L - 1.59")[0]

    assert item.incoming_name == "Coca Cola 2L"
    assert item.price == Decimal("1.59")
    assert item.currency == "EUR"


def test_comma_decimal_price() -> None:
    item = parse_campaign_text("Pinar Sut 1L 0,89")[0]

    assert item.price == Decimal("0.89")


def test_euro_suffix() -> None:
    item = parse_campaign_text("Eti Burcak - 0.99€")[0]

    assert item.price == Decimal("0.99")
    assert item.currency == "EUR"


def test_euro_prefix() -> None:
    item = parse_campaign_text("Eti Burcak - €0.99")[0]

    assert item.price == Decimal("0.99")
    assert item.currency == "EUR"


def test_colon_separator() -> None:
    item = parse_campaign_text("Eti Burcak: 0.99")[0]

    assert item.incoming_name == "Eti Burcak"
    assert item.price == Decimal("0.99")


def test_pipe_separator() -> None:
    item = parse_campaign_text("Eti Burcak | 0.99")[0]

    assert item.incoming_name == "Eti Burcak"
    assert item.price == Decimal("0.99")


def test_tab_separator() -> None:
    item = parse_campaign_text("Eti Burcak\t0.99")[0]

    assert item.incoming_name == "Eti Burcak"
    assert item.price == Decimal("0.99")


def test_space_before_price_at_end() -> None:
    item = parse_campaign_text("Pinar Sut 1L 0,89")[0]

    assert item.incoming_name == "Pinar Sut 1L"
    assert item.price == Decimal("0.89")


def test_no_price_returns_warning_and_null_price() -> None:
    item = parse_campaign_text("Coca Cola 2L")[0]

    assert item.price is None
    assert item.parsed_payload["warnings"] == ["no_price_found"]


def test_old_new_arrow_price_pattern() -> None:
    item = parse_campaign_text("Coca Cola 2L - 1.99€ -> 1.59€")[0]

    assert item.incoming_name == "Coca Cola 2L"
    assert item.old_price == Decimal("1.99")
    assert item.price == Decimal("1.59")


def test_old_new_words_price_pattern() -> None:
    item = parse_campaign_text("Coca Cola 2L old 1.99 new 1.59")[0]

    assert item.incoming_name == "Coca Cola 2L"
    assert item.old_price == Decimal("1.99")
    assert item.price == Decimal("1.59")


def test_multiple_lines_preserve_order() -> None:
    items = parse_campaign_text("A - 1.00\n\nB - 2.00\nC - 3.00")

    assert [item.incoming_name for item in items] == ["A", "B", "C"]
    assert [item.sort_order for item in items] == [0, 1, 2]


def test_product_name_cleanup_preserves_package_text() -> None:
    assert clean_product_name("Coca Cola 2L -") == "Coca Cola 2L"
    assert clean_product_name("Torku Sucuk 400g -") == "Torku Sucuk 400g"
    assert clean_product_name("Ulker Halley 10'lu -") == "Ulker Halley 10'lu"


def test_parse_price_supports_dot_and_comma() -> None:
    assert parse_price("1.59") == Decimal("1.59")
    assert parse_price("1,59") == Decimal("1.59")
