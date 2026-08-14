from app.services.product_identity import normalize_product_identity


def _identity(value: str) -> str:
    return normalize_product_identity(value).normalized_full_name


def test_turkish_catalog_identity_prevents_equivalent_name_duplicates() -> None:
    canonical = _identity("Sütaş Yoğurt")
    assert canonical == _identity("Sutas Yogurt")
    assert canonical == _identity("  SÜTAŞ--yoğurt  ")
    assert canonical == _identity("Sütaş, Yoğurt")


def test_turkish_catalog_identity_handles_package_and_case_variations() -> None:
    assert _identity("Sütaş Yoğurt 1 L") == _identity("sutas yogurt 1000ml")