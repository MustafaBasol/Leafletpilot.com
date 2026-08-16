from decimal import Decimal
from uuid import uuid4

from app.models import Brand, BrandAlias, Product, ProductAlias, ProductImage
from app.services.catalog import normalize_alias
from app.services.catalog_quality import build_quality_candidates, ordered_product_pair


def _product(
    name: str,
    *,
    barcode: str | None = None,
    brand_name: str = "Sütaş",
    package_size: str = "1 L",
    package_amount: Decimal | None = None,
    package_unit: str | None = None,
    aliases: tuple[str, ...] = (),
    image: bool = False,
) -> Product:
    brand = Brand(
        id=uuid4(),
        name=brand_name,
        slug=f"brand-{uuid4().hex}",
        is_global=True,
        aliases=[
            BrandAlias(alias=brand_name, normalized_alias=brand_name.casefold())
        ],
    )
    product = Product(
        id=uuid4(),
        name=name,
        barcode=barcode,
        package_size=package_size,
        package_amount=package_amount,
        package_unit=package_unit,
        is_global=True,
        is_active=True,
        brand=brand,
        aliases=[
            ProductAlias(alias=alias, normalized_alias=normalize_alias(alias))
            for alias in aliases
        ],
    )
    if image:
        product.images = [
            ProductImage(
                id=uuid4(),
                storage_key=f"catalog/{product.id}.webp",
                quality_status="good",
                is_primary=True,
            )
        ]
    return product


def _single(products, *, ignored_pairs=None, include_ignored=False):
    result = build_quality_candidates(
        products,
        ignored_pairs=ignored_pairs,
        include_ignored=include_ignored,
    )
    assert len(result.items) == 1
    return result.items[0]


def test_same_normalized_barcode_and_identity_is_an_exact_duplicate() -> None:
    first = _product("Sütaş Yoğurt", barcode="869-123 456", image=True)
    second = _product("Sutas Yogurt", barcode="869123456", image=True)

    candidate = _single([first, second])

    assert candidate["state"] == "exact_duplicate"
    assert candidate["merge_allowed"] is True
    assert candidate["product_a"]["image_url"]


def test_same_canonical_identity_brand_and_package_is_an_exact_duplicate() -> None:
    first = _product("Sütaş Yoğurt", package_size="1 L")
    second = _product("sutas yogurt", package_size="1000 ml")

    candidate = _single([first, second])

    assert candidate["state"] == "exact_duplicate"
    assert candidate["merge_allowed"] is True


def test_alias_driven_match_is_a_reviewable_strong_candidate() -> None:
    first = _product("Sütaş Protein Yoğurt", aliases=("Sütaş Fit Yoğurt",))
    second = _product("Sutas Fit Yogurt")

    candidate = _single([first, second])

    assert candidate["state"] in {"exact_duplicate", "strong_candidate"}
    assert any("shared alias" in value for value in candidate["matching_fields"])


def test_package_difference_prevents_duplicate_collapse() -> None:
    first = _product("Sütaş Yoğurt", package_size="100 g")
    second = _product("Sutas Yogurt", package_size="500 g")

    candidate = _single([first, second])

    assert candidate["state"] in {"identity_conflict", "alias_conflict"}
    assert candidate["merge_allowed"] is False
    assert any("package" in blocker.casefold() for blocker in candidate["blockers"])


def test_different_brand_and_same_barcode_is_a_blocking_barcode_conflict() -> None:
    first = _product("Yoğurt", barcode="869123456", brand_name="Sütaş")
    second = _product("Yoğurt", barcode="869123456", brand_name="Pınar")

    candidate = _single([first, second])

    assert candidate["state"] == "barcode_conflict"
    assert candidate["merge_allowed"] is False


def test_ignore_pair_is_not_returned_as_an_unresolved_candidate() -> None:
    first = _product("Sütaş Yoğurt", barcode="869123456")
    second = _product("Sutas Yogurt", barcode="869123456")
    ignored = {ordered_product_pair(first.id, second.id)}

    hidden = build_quality_candidates([first, second], ignored_pairs=ignored)
    shown = build_quality_candidates([first, second], ignored_pairs=ignored, include_ignored=True)

    assert hidden.items == []
    assert shown.items[0]["state"] == "ignored"