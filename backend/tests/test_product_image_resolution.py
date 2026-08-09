from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import CampaignItem, MarketProduct, Product, ProductAlias, ProductImage
from app.schemas.product import ProductAliasCreate
from app.services import catalog as catalog_service
from app.services.product_identity import normalize_product_identity, normalize_product_text
from app.services.product_image_resolution import (
    CurrentAssignmentProvider,
    ImageCandidate,
    ImageResolutionResult,
    InternalCatalogProvider,
    ProductImageResolver,
    ResolutionContext,
    _apply_resolution,
)


def _candidate(
    name: str,
    *,
    brand: str | None = None,
    package_size: str | None = None,
    aliases: tuple[str, ...] = (),
    storage_key: str = "products/example.png",
) -> ImageCandidate:
    return ImageCandidate(
        identity=normalize_product_identity(name, brand=brand, package_size=package_size),
        aliases=tuple(normalize_product_identity(alias) for alias in aliases),
        image_storage_key=storage_key,
        image_url=None,
        image_mime_type="image/png",
        image_has_alpha=True,
        product_id=uuid4(),
        market_product_id=None,
        catalog_scope="global",
    )


def _context(name: str, *candidates: ImageCandidate) -> ResolutionContext:
    return ResolutionContext(
        item=CampaignItem(
            id=uuid4(),
            market_id=uuid4(),
            raw_line=f"{name} - 29,90",
            incoming_name=name,
            price=Decimal("29.90"),
        ),
        identity=normalize_product_identity(name),
        catalog_candidates=tuple(candidates),
        historical_candidates=(),
    )


@pytest.mark.parametrize(
    "value",
    ["Coca Cola 1L", "Coca-Cola 1 lt", "COCA COLA 1000 ml"],
)
def test_coca_cola_quantity_forms_share_one_identity(value: str) -> None:
    assert normalize_product_text(value) == "coca cola 1000ml"


def test_case_spacing_punctuation_turkish_units_pack_and_percent_normalize() -> None:
    assert normalize_product_text("  SÜTAŞ--Yoğurt, 1 kilogram!! ") == "sutas yogurt 1000g"
    assert normalize_product_text("Süt 1,5 litre") == "sut 1500ml"
    assert normalize_product_text("Eti Burçak 2'li") == "eti burcak 2x"
    assert normalize_product_text("Yoğurt %3,5") == normalize_product_text("Yoğurt 3.5%")


@pytest.mark.asyncio
async def test_exact_existing_image_and_uploaded_override_win() -> None:
    product = Product(
        id=uuid4(),
        name="Coca Cola 1L",
        is_global=True,
        images=[
            ProductImage(
                storage_key="global/coca-cola.png",
                is_primary=True,
                quality_status="good",
                mime_type="image/png",
            )
        ],
    )
    market_product = MarketProduct(
        id=uuid4(),
        market_id=uuid4(),
        product_id=product.id,
        product=product,
        image_storage_key="markets/uploaded-coca-cola.png",
        image_mime_type="image/png",
        image_quality_status="good",
    )
    item = CampaignItem(
        id=uuid4(),
        market_id=market_product.market_id,
        raw_line="Coca Cola 1L - 29,90",
        incoming_name="Coca Cola 1L",
        product_id=product.id,
        market_product_id=market_product.id,
        product=product,
        market_product=market_product,
    )
    context = ResolutionContext(
        item=item,
        identity=normalize_product_identity(item.incoming_name),
        catalog_candidates=(_candidate("Coca Cola 1L", storage_key="wrong.png"),),
        historical_candidates=(),
    )

    result = await ProductImageResolver(
        providers=(CurrentAssignmentProvider(), InternalCatalogProvider())
    ).resolve(context)

    assert result.image_storage_key == "markets/uploaded-coca-cola.png"
    assert result.source == "explicit_market_image"
    assert result.confidence == Decimal("1.00")


@pytest.mark.asyncio
async def test_same_product_tenant_override_beats_global_current_image() -> None:
    product_id = uuid4()
    product = Product(
        id=product_id,
        name="Coca Cola 1L",
        is_global=True,
        images=[
            ProductImage(
                storage_key="global/coca-cola.png",
                is_primary=True,
                quality_status="good",
            )
        ],
    )
    market_candidate = _candidate("Coca Cola 1L", storage_key="markets/coca-cola-override.png")
    market_candidate = ImageCandidate(
        **{
            **market_candidate.__dict__,
            "product_id": product_id,
            "market_product_id": uuid4(),
            "catalog_scope": "market",
        }
    )
    item = CampaignItem(
        id=uuid4(),
        market_id=uuid4(),
        raw_line="Coca Cola 1L - 29,90",
        incoming_name="Coca Cola 1L",
        product_id=product_id,
        product=product,
    )
    context = ResolutionContext(
        item=item,
        identity=normalize_product_identity(item.incoming_name),
        catalog_candidates=(market_candidate,),
        historical_candidates=(),
    )

    result = await ProductImageResolver(
        providers=(CurrentAssignmentProvider(), InternalCatalogProvider())
    ).resolve(context)
    _apply_resolution(item, result)

    assert result.image_storage_key == "markets/coca-cola-override.png"
    assert result.source == "explicit_market_image"
    assert item.market_product_id == market_candidate.market_product_id


@pytest.mark.asyncio
async def test_exact_alias_and_normalized_catalog_identity_resolve() -> None:
    alias_candidate = _candidate(
        "Coca Cola Original 1L",
        brand="Coca Cola",
        aliases=("Kola Klasik 1 LT",),
    )
    alias_result = await InternalCatalogProvider().resolve(
        _context("Kola Klasik 1000 ml", alias_candidate)
    )
    normalized_result = await InternalCatalogProvider().resolve(
        _context("COCA-COLA 1000 ML", _candidate("Coca Cola 1L", brand="Coca Cola"))
    )

    assert alias_result is not None
    assert alias_result.source == "exact_alias"
    assert alias_result.confidence == Decimal("0.99")
    assert alias_result.requires_review is False
    assert normalized_result is not None
    assert normalized_result.confidence == Decimal("1.00")
    assert normalized_result.resolved is True


@pytest.mark.asyncio
async def test_size_and_variant_conflicts_reject_unsafe_images() -> None:
    size_result = await InternalCatalogProvider().resolve(
        _context("Coca Cola 1L", _candidate("Coca Cola 2L", brand="Coca Cola"))
    )
    variant_result = await InternalCatalogProvider().resolve(
        _context(
            "Coca Cola Zero 1L",
            _candidate("Coca Cola Original 1L", brand="Coca Cola"),
        )
    )

    assert size_result is None
    assert variant_result is None


@pytest.mark.asyncio
async def test_missing_size_evidence_remains_below_automatic_threshold() -> None:
    candidate = _candidate("Eti Burçak 500g", brand="Eti")
    context = _context("Eti Burçak", candidate)
    result = await ProductImageResolver(providers=(InternalCatalogProvider(),)).resolve(context)

    assert result.confidence < Decimal("0.90")
    assert result.requires_review is True
    assert result.resolved is False


@pytest.mark.asyncio
async def test_unrelated_candidate_returns_safe_fallback() -> None:
    context = _context("Eti Burçak", _candidate("Sütaş Yoğurt", brand="Sütaş"))
    result = await ProductImageResolver(providers=(InternalCatalogProvider(),)).resolve(context)

    assert result.source == "fallback"
    assert result.resolved is False
    assert result.image_storage_key is None


@pytest.mark.asyncio
async def test_duplicate_alias_is_rejected_within_market_scope(monkeypatch) -> None:
    market_id = uuid4()
    product = Product(id=uuid4(), name="Coca Cola 1L", market_id=market_id, is_global=False)
    duplicate = ProductAlias(
        id=uuid4(),
        product_id=uuid4(),
        alias="Coca-Cola 1 lt",
        normalized_alias="coca cola 1000ml",
    )

    class Session:
        async def scalar(self, _statement):
            return duplicate

    async def get_product(*_args, **_kwargs):
        return product

    monkeypatch.setattr(catalog_service, "get_product", get_product)

    with pytest.raises(HTTPException) as error:
        await catalog_service.create_product_alias(
            Session(),
            product.id,
            ProductAliasCreate(alias="Coca Cola 1000 ml"),
            market_id,
        )

    assert error.value.status_code == 409


class _FailingProvider:
    name = "failing"

    async def resolve(self, _context):
        raise RuntimeError("provider unavailable")


class _FixedProvider:
    def __init__(self, name: str, result: ImageResolutionResult):
        self.name = name
        self.result = result
        self.calls = 0

    async def resolve(self, _context):
        self.calls += 1
        return self.result


@pytest.mark.asyncio
async def test_provider_ordering_and_failure_isolation() -> None:
    context = _context("Eti Burçak")
    identity = context.identity
    high = ImageResolutionResult(
        image_storage_key="products/eti-burcak.png",
        image_url=None,
        image_mime_type="image/png",
        image_has_alpha=True,
        source="exact_catalog_identity",
        confidence=Decimal("1.00"),
        matched_product_id=uuid4(),
        matched_market_product_id=None,
        match_reason="exact",
        requires_review=False,
        normalized_identity=identity,
        provider="fixed",
    )
    first = _FixedProvider("first", high)
    never = _FixedProvider("never", high)

    result = await ProductImageResolver(providers=(_FailingProvider(), first, never)).resolve(
        context
    )

    assert result.image_storage_key == "products/eti-burcak.png"
    assert first.calls == 1
    assert never.calls == 0


def test_resolution_metadata_does_not_mutate_campaign_facts_and_survives_rerender_edits() -> None:
    candidate = _candidate("Sütaş Yoğurt", brand="Sütaş")
    context = _context("Sütaş Yoğurt", candidate)
    item = context.item
    original = (item.incoming_name, item.raw_line, item.price, item.display_name)
    result = ImageResolutionResult(
        image_storage_key=candidate.image_storage_key,
        image_url=None,
        image_mime_type="image/png",
        image_has_alpha=True,
        source="exact_catalog_identity",
        confidence=Decimal("1.00"),
        matched_product_id=candidate.product_id,
        matched_market_product_id=None,
        match_reason="exact",
        requires_review=False,
        normalized_identity=context.identity,
        provider="internal_catalog",
    )

    _apply_resolution(item, result)
    item.is_hero = True
    _apply_resolution(item, result)

    assert (item.incoming_name, item.raw_line, item.price, item.display_name) == original
    assert item.product_id == candidate.product_id
    assert item.parsed_payload["image_resolution"]["decision"] == "resolved"


@pytest.mark.asyncio
async def test_representative_three_product_acceptance_fixture() -> None:
    fixtures = (
        (
            "Coca Cola 1L",
            _candidate("Coca-Cola 1000 ml", brand="Coca Cola", storage_key="coca.png"),
        ),
        ("Eti Burçak", _candidate("Eti Burçak", brand="Eti", storage_key="burcak.png")),
        ("Sütaş Yoğurt", _candidate("Sütaş Yoğurt", brand="Sütaş", storage_key="yogurt.png")),
    )

    report = []
    for product_input, candidate in fixtures:
        context = _context(product_input, candidate)
        result = await ProductImageResolver(providers=(InternalCatalogProvider(),)).resolve(context)
        report.append(
            (
                product_input,
                context.identity.normalized_full_name,
                result.source,
                result.confidence,
                result.resolved,
            )
        )

    assert report == [
        ("Coca Cola 1L", "coca cola 1000ml", "exact_catalog_identity", Decimal("1.00"), True),
        ("Eti Burçak", "eti burcak", "exact_catalog_identity", Decimal("1.00"), True),
        ("Sütaş Yoğurt", "sutas yogurt", "exact_catalog_identity", Decimal("1.00"), True),
    ]
