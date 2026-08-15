"""Phase 28B catalog-entry matching and market-product integrity regressions.

The HTTP tests deliberately exercise the mutation endpoints as well as the
advisory match endpoint.  This keeps duplicate and tenant guarantees enforced
even when a client skips the preliminary match request.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models
from app.api.deps import get_catalog_session, get_current_user
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.models import (
    Brand,
    BrandAlias,
    Category,
    Market,
    MarketProduct,
    MarketUser,
    Product,
    ProductAlias,
    User,
)
from app.services.campaign import validate_visible_market_product
from app.services.catalog import normalize_alias, resolved_market_product


@dataclass(frozen=True)
class CatalogContext:
    session_factory: async_sessionmaker
    client: httpx.AsyncClient
    market_a_id: UUID
    market_b_id: UUID
    user_id: UUID
    global_brand_id: UUID
    local_brand_b_id: UUID
    structured_product_id: UUID
    structured_barcode: str
    size_variant_id: UUID
    inactive_product_id: UUID
    inactive_barcode: str

    def headers(self, market_id: UUID | None = None) -> dict[str, str]:
        return {"X-Market-Id": str(market_id or self.market_a_id)}


def _barcode() -> str:
    return f"869{uuid4().int % 10_000_000_000:010d}"


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def catalog_context() -> CatalogContext:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; catalog matching tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    suffix = uuid4().hex[:10]
    market_a_id, market_b_id, user_id = uuid4(), uuid4(), uuid4()
    global_brand_id, local_brand_b_id = uuid4(), uuid4()
    structured_product_id, size_variant_id, inactive_product_id = uuid4(), uuid4(), uuid4()
    structured_barcode, inactive_barcode = _barcode(), _barcode()

    async with session_factory() as session:
        global_brand = Brand(
            id=global_brand_id,
            name="Ülker",
            slug=f"ulker-{suffix}",
            is_global=True,
            market_id=None,
        )
        global_brand.aliases = [
            BrandAlias(alias="Ulker", normalized_alias=normalize_alias("Ulker")),
        ]
        local_brand_b = Brand(
            id=local_brand_b_id,
            name="Market B Gizli Marka",
            slug=f"market-b-secret-{suffix}",
            is_global=False,
            market_id=market_b_id,
        )
        local_brand_b.aliases = [
            BrandAlias(alias="Ulker", normalized_alias=normalize_alias("Ulker"))
        ]
        session.add_all(
            [
                Market(
                    id=market_a_id,
                    name=f"Catalog Match A {suffix}",
                    slug=f"catalog-match-a-{suffix}",
                    subscription_plan="growth",
                ),
                Market(
                    id=market_b_id,
                    name=f"Catalog Match B {suffix}",
                    slug=f"catalog-match-b-{suffix}",
                    subscription_plan="growth",
                ),
                User(id=user_id, email=f"catalog-match-{suffix}@example.test", is_active=True),
            ]
        )
        await session.flush()
        session.add_all(
            [
                MarketUser(
                    market_id=market_a_id,
                    user_id=user_id,
                    role="market_admin",
                    is_active=True,
                ),
                MarketUser(
                    market_id=market_b_id,
                    user_id=user_id,
                    role="market_admin",
                    is_active=True,
                ),
                global_brand,
                local_brand_b,
            ]
        )
        await session.flush()
        session.add_all(
            [
                Product(
                    id=structured_product_id,
                    name="Çokokrem",
                    barcode=structured_barcode,
                    brand_id=global_brand_id,
                    package_size="400 g",
                    package_amount=Decimal(400),
                    package_unit="g",
                    package_type="jar",
                    package_type_canonical="jar",
                    is_global=True,
                    market_id=None,
                    is_active=True,
                ),
                Product(
                    id=size_variant_id,
                    name="Çokokrem",
                    barcode=_barcode(),
                    brand_id=global_brand_id,
                    package_size="750 g",
                    package_amount=Decimal(750),
                    package_unit="g",
                    package_type="jar",
                    package_type_canonical="jar",
                    is_global=True,
                    market_id=None,
                    is_active=True,
                ),
                Product(
                    id=inactive_product_id,
                    name=f"Inactive Match {suffix}",
                    barcode=inactive_barcode,
                    brand_id=global_brand_id,
                    package_size="100 g",
                    package_amount=Decimal(100),
                    package_unit="g",
                    is_global=True,
                    market_id=None,
                    is_active=False,
                ),
            ]
        )
        await session.commit()

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_user():
        return User(
            id=user_id,
            email=f"catalog-match-{suffix}@example.test",
            is_active=True,
        )

    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield CatalogContext(
                session_factory=session_factory,
                client=client,
                market_a_id=market_a_id,
                market_b_id=market_b_id,
                user_id=user_id,
                global_brand_id=global_brand_id,
                local_brand_b_id=local_brand_b_id,
                structured_product_id=structured_product_id,
                structured_barcode=structured_barcode,
                size_variant_id=size_variant_id,
                inactive_product_id=inactive_product_id,
                inactive_barcode=inactive_barcode,
            )
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


async def _seed_product(
    context: CatalogContext,
    *,
    name: str,
    barcode: str | None = None,
    brand_id: UUID | None = None,
    package_size: str | None = None,
    package_amount: Decimal | None = None,
    package_unit: str | None = None,
    package_type: str | None = None,
    package_type_canonical: str | None = None,
    regular_price: Decimal | None = None,
    badge_text: str | None = None,
    is_global: bool = True,
    market_id: UUID | None = None,
    is_active: bool = True,
) -> UUID:
    product_id = uuid4()
    async with context.session_factory() as session:
        session.add(
            Product(
                id=product_id,
                name=name,
                barcode=barcode,
                brand_id=brand_id,
                package_size=package_size,
                package_amount=package_amount,
                package_unit=package_unit,
                package_type=package_type,
                package_type_canonical=package_type_canonical,
                regular_price=regular_price,
                badge_text=badge_text,
                is_global=is_global,
                market_id=market_id,
                is_active=is_active,
            )
        )
        await session.commit()
    return product_id


async def _seed_market_product(
    context: CatalogContext,
    *,
    market_id: UUID,
    product_id: UUID | None = None,
    private_name: str | None = None,
    **values,
) -> UUID:
    market_product_id = uuid4()
    async with context.session_factory() as session:
        session.add(
            MarketProduct(
                id=market_product_id,
                market_id=market_id,
                product_id=product_id,
                private_name=private_name,
                **values,
            )
        )
        await session.commit()
    return market_product_id


async def _match(context: CatalogContext, payload: dict, market_id: UUID | None = None):
    return await context.client.post(
        "/api/catalog/products/match",
        headers=context.headers(market_id),
        json=payload,
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_barcode_precedence_structured_fallback_inactive_and_no_fuzzy(
    catalog_context: CatalogContext,
) -> None:
    exact = await _match(
        catalog_context,
        {"name": "Completely different name", "barcode": catalog_context.structured_barcode},
    )
    assert exact.status_code == 200, exact.text
    exact_body = exact.json()
    assert exact_body["match_type"] == "exact"
    assert exact_body["candidate_count"] == 1
    assert exact_body["candidates"][0]["product_id"] == str(catalog_context.structured_product_id)
    assert "barcode" in exact_body["match_reason"].casefold()
    assert exact_body["candidates"][0]["already_adopted"] is False

    fallback = await _match(
        catalog_context,
        {
            "name": "ulker cokokrem",
            "barcode": _barcode(),
            "brand": "ULKER",
            "package_size": "400gr",
        },
    )
    assert fallback.status_code == 200, fallback.text
    assert fallback.json()["match_type"] == "strong"
    assert fallback.json()["candidates"][0]["product_id"] == str(
        catalog_context.structured_product_id
    )

    inactive = await _match(
        catalog_context,
        {
            "name": "irrelevant inactive lookup",
            "barcode": catalog_context.inactive_barcode,
        },
    )
    assert inactive.status_code == 200, inactive.text
    assert inactive.json()["match_type"] == "none"
    assert inactive.json()["candidate_count"] == 0

    fuzzy = await _match(
        catalog_context,
        {
            "name": "cokokrm",
            "brand": "ulker",
            "package_amount": "400",
            "package_unit": "g",
        },
    )
    assert fuzzy.status_code == 200, fuzzy.text
    assert fuzzy.json()["match_type"] == "none"
    assert fuzzy.json()["candidates"] == []


@pytest.mark.asyncio(loop_scope="module")
async def test_structured_identity_reuses_brand_alias_and_keeps_size_variants_distinct(
    catalog_context: CatalogContext,
) -> None:
    by_alias = await _match(
        catalog_context,
        {
            "name": "ÜLKER ÇOKOKREM",
            "brand": "ulker",
            "package_size": "400 g",
            "package_type": "kavanoz",
        },
    )
    assert by_alias.status_code == 200, by_alias.text
    body = by_alias.json()
    assert body["match_type"] == "strong"
    assert body["candidate_count"] == 1
    assert body["candidates"][0]["product_id"] == str(catalog_context.structured_product_id)

    by_brand_id = await _match(
        catalog_context,
        {
            "name": "çokokrem",
            "brand_id": str(catalog_context.global_brand_id),
            "package_amount": "750",
            "package_unit": "g",
            "package_type_canonical": "jar",
        },
    )
    assert by_brand_id.status_code == 200, by_brand_id.text
    variant_body = by_brand_id.json()
    assert variant_body["match_type"] == "strong"
    assert variant_body["candidate_count"] == 1
    assert variant_body["candidates"][0]["product_id"] == str(catalog_context.size_variant_id)

    product_alias = f"Catalog Alias {uuid4().hex[:8]}"
    alias_product_id = await _seed_product(
        catalog_context,
        name=f"Canonical Spread {uuid4().hex[:8]}",
        brand_id=catalog_context.global_brand_id,
        package_size="250 g",
        package_amount=Decimal(250),
        package_unit="g",
    )
    async with catalog_context.session_factory() as session:
        session.add(
            ProductAlias(
                product_id=alias_product_id,
                alias=product_alias,
                normalized_alias=normalize_alias(product_alias),
            )
        )
        await session.commit()
    by_product_alias = await _match(
        catalog_context,
        {
            "name": product_alias,
            "brand": "Ulker",
            "package_size": "250gr",
        },
    )
    assert by_product_alias.status_code == 200, by_product_alias.text
    assert by_product_alias.json()["match_type"] == "strong"
    assert by_product_alias.json()["candidates"][0]["product_id"] == str(alias_product_id)


@pytest.mark.asyncio(loop_scope="module")
async def test_barcode_and_structured_collisions_are_ambiguous_and_read_only(
    catalog_context: CatalogContext,
) -> None:
    collision_barcode = _barcode()
    barcode_ids = set()
    for label in "ABCDEFG":
        barcode_ids.add(
            await _seed_product(
                catalog_context,
                name=f"Barcode Collision {label} {uuid4().hex[:6]}",
                barcode=collision_barcode,
            )
        )
    response = await _match(
        catalog_context,
        {"name": "No identity evidence", "barcode": collision_barcode},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["match_type"] == "ambiguous"
    assert payload["candidate_count"] == 7
    assert len(payload["candidates"]) == 5
    assert {UUID(candidate["product_id"]) for candidate in payload["candidates"]} < barcode_ids

    formatted_barcode = _barcode()
    formatted_ids = {
        await _seed_product(
            catalog_context,
            name=f"Slash Barcode {uuid4().hex[:6]}",
            barcode=f"{formatted_barcode[:3]}/{formatted_barcode[3:]}",
        ),
        await _seed_product(
            catalog_context,
            name=f"Dash Barcode {uuid4().hex[:6]}",
            barcode=f"{formatted_barcode[:3]}-{formatted_barcode[3:]}",
        ),
    }
    formatted = await _match(
        catalog_context,
        {"name": "No structured evidence", "barcode": formatted_barcode},
    )
    assert formatted.status_code == 200, formatted.text
    assert formatted.json()["match_type"] == "ambiguous"
    assert formatted.json()["candidate_count"] == 2
    assert {
        UUID(candidate["product_id"]) for candidate in formatted.json()["candidates"]
    } == formatted_ids

    alpha_digits = _barcode()
    alpha_id = await _seed_product(
        catalog_context,
        name=f"Alphanumeric Identifier {uuid4().hex[:6]}",
        barcode=f"SKU{alpha_digits}",
    )
    alpha_collision = await _match(
        catalog_context,
        {"name": "No structured evidence", "barcode": alpha_digits},
    )
    assert alpha_collision.status_code == 200, alpha_collision.text
    assert alpha_collision.json()["match_type"] == "none"

    alpha_exact = await _match(
        catalog_context,
        {"name": "No structured evidence", "barcode": f"sku{alpha_digits}"},
    )
    assert alpha_exact.status_code == 200, alpha_exact.text
    assert alpha_exact.json()["match_type"] == "exact"
    assert alpha_exact.json()["candidates"][0]["product_id"] == str(alpha_id)

    identity_name = f"Ambiguous Wafer {uuid4().hex[:8]}"
    identity_ids = {
        await _seed_product(
            catalog_context,
            name=identity_name,
            brand_id=catalog_context.global_brand_id,
            package_size="90 g",
            package_amount=Decimal(90),
            package_unit="g",
        ),
        await _seed_product(
            catalog_context,
            name=identity_name,
            brand_id=catalog_context.global_brand_id,
            package_size="90gr",
            package_amount=Decimal(90),
            package_unit="g",
        ),
    }
    before_count: int
    async with catalog_context.session_factory() as session:
        before_count = int(
            await session.scalar(
                select(func.count(MarketProduct.id)).where(
                    MarketProduct.market_id == catalog_context.market_a_id
                )
            )
            or 0
        )
    structured = await _match(
        catalog_context,
        {
            "name": identity_name,
            "brand": "Ulker",
            "package_size": "90 g",
        },
    )
    assert structured.status_code == 200, structured.text
    structured_body = structured.json()
    assert structured_body["match_type"] == "ambiguous"
    assert {
        UUID(candidate["product_id"]) for candidate in structured_body["candidates"]
    } == identity_ids

    bounded_name = f"ZetaBounded {uuid4().hex[:8]} Target"
    bounded_token = bounded_name.split()[0]
    bounded_ids = {uuid4(), uuid4()}
    async with catalog_context.session_factory() as session:
        session.add_all(
            [
                Product(
                    id=uuid4(),
                    name=f"A {bounded_token} Noise {index:03d}",
                    brand_id=catalog_context.global_brand_id,
                    package_size="125 g",
                    package_amount=Decimal(125),
                    package_unit="g",
                    is_global=True,
                    market_id=None,
                    is_active=True,
                )
                for index in range(99)
            ]
            + [
                Product(
                    id=product_id,
                    name=bounded_name,
                    brand_id=catalog_context.global_brand_id,
                    package_size="125 g",
                    package_amount=Decimal(125),
                    package_unit="g",
                    is_global=True,
                    market_id=None,
                    is_active=True,
                )
                for product_id in bounded_ids
            ]
        )
        await session.commit()
    bounded = await _match(
        catalog_context,
        {"name": bounded_name, "brand": "Ulker", "package_size": "125 g"},
    )
    assert bounded.status_code == 200, bounded.text
    bounded_body = bounded.json()
    assert bounded_body["match_type"] == "ambiguous"
    assert bounded_body["match_reason"] == "candidate search truncated"
    assert {UUID(candidate["product_id"]) for candidate in bounded_body["candidates"]} < bounded_ids

    async with catalog_context.session_factory() as session:
        session.add(
            Product(
                id=uuid4(),
                name=f"A {bounded_token} Noise 999",
                brand_id=catalog_context.global_brand_id,
                package_size="125 g",
                package_amount=Decimal(125),
                package_unit="g",
                is_global=True,
                market_id=None,
                is_active=True,
            )
        )
        await session.commit()
    fully_hidden = await _match(
        catalog_context,
        {"name": bounded_name, "brand": "Ulker", "package_size": "125 g"},
    )
    assert fully_hidden.status_code == 200, fully_hidden.text
    assert fully_hidden.json()["match_type"] == "ambiguous"
    assert fully_hidden.json()["match_reason"] == "candidate search truncated"
    assert fully_hidden.json()["candidates"] == []

    async with catalog_context.session_factory() as session:
        after_count = int(
            await session.scalar(
                select(func.count(MarketProduct.id)).where(
                    MarketProduct.market_id == catalog_context.market_a_id
                )
            )
            or 0
        )
    assert after_count == before_count

    first_formatted_id, second_formatted_id = tuple(formatted_ids)
    first_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{first_formatted_id}/adopt",
        headers=catalog_context.headers(),
    )
    assert first_adoption.status_code == 201, first_adoption.text
    duplicate_global_identity = await catalog_context.client.post(
        f"/api/catalog/shared/{second_formatted_id}/adopt",
        headers=catalog_context.headers(),
    )
    assert duplicate_global_identity.status_code == 409

    first_identity_id, second_identity_id = tuple(identity_ids)
    first_identity_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{first_identity_id}/adopt",
        headers=catalog_context.headers(),
    )
    assert first_identity_adoption.status_code == 201, first_identity_adoption.text
    second_identity_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{second_identity_id}/adopt",
        headers=catalog_context.headers(),
    )
    assert second_identity_adoption.status_code == 409


@pytest.mark.asyncio(loop_scope="module")
async def test_duplicate_and_concurrent_global_adoption_return_conflict(
    catalog_context: CatalogContext,
) -> None:
    barcode = _barcode()
    product_id = await _seed_product(
        catalog_context,
        name=f"Concurrent Adoption {uuid4().hex[:8]}",
        barcode=barcode,
    )
    path = f"/api/catalog/shared/{product_id}/adopt"
    first, second = await asyncio.gather(
        catalog_context.client.post(path, headers=catalog_context.headers()),
        catalog_context.client.post(path, headers=catalog_context.headers()),
    )
    assert sorted((first.status_code, second.status_code)) == [201, 409]
    repeated = await catalog_context.client.post(path, headers=catalog_context.headers())
    assert repeated.status_code == 409
    async with catalog_context.session_factory() as session:
        count = await session.scalar(
            select(func.count(MarketProduct.id)).where(
                MarketProduct.market_id == catalog_context.market_a_id,
                MarketProduct.product_id == product_id,
            )
        )
    assert count == 1

    local_barcode = _barcode()
    local_payload = {
        "private_name": f"Concurrent Local {uuid4().hex[:8]}",
        "private_brand_text": "Concurrent Brand",
        "private_barcode": local_barcode,
        "private_package_size": "330 ml",
    }
    first_local, second_local = await asyncio.gather(
        catalog_context.client.post(
            "/api/catalog/private-products",
            headers=catalog_context.headers(),
            json=local_payload,
        ),
        catalog_context.client.post(
            "/api/catalog/private-products",
            headers=catalog_context.headers(),
            json=local_payload,
        ),
    )
    assert sorted((first_local.status_code, second_local.status_code)) == [201, 409]
    async with catalog_context.session_factory() as session:
        local_count = await session.scalar(
            select(func.count(MarketProduct.id)).where(
                MarketProduct.market_id == catalog_context.market_a_id,
                MarketProduct.private_barcode == local_barcode,
            )
        )
    assert local_count == 1

    local_shadow = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Local Shadow {uuid4().hex[:8]}",
            "private_barcode": barcode,
            "allow_global_match_override": True,
        },
    )
    assert local_shadow.status_code == 409


@pytest.mark.asyncio(loop_scope="module")
async def test_effective_identity_guards_adopt_patch_and_link_paths(
    catalog_context: CatalogContext,
) -> None:
    suffix = uuid4().hex[:8]
    local_barcode = _barcode()
    existing_local = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Effective Local {suffix}",
            "private_brand_text": "Effective Brand",
            "private_barcode": local_barcode,
            "private_package_size": "330 ml",
        },
    )
    assert existing_local.status_code == 201, existing_local.text

    global_barcode = _barcode()
    global_id = await _seed_product(
        catalog_context,
        name=f"Effective Global {suffix}",
        barcode=global_barcode,
        package_size="1 l",
        package_amount=Decimal(1),
        package_unit="l",
    )
    override_collision = await catalog_context.client.post(
        f"/api/catalog/shared/{global_id}/adopt",
        headers=catalog_context.headers(),
        json={
            "product_id": str(global_id),
            "private_barcode": local_barcode,
        },
    )
    assert override_collision.status_code == 409

    adopted = await catalog_context.client.post(
        f"/api/catalog/shared/{global_id}/adopt",
        headers=catalog_context.headers(),
    )
    assert adopted.status_code == 201, adopted.text
    adopted_patch = await catalog_context.client.patch(
        f"/api/catalog/my-products/{adopted.json()['id']}",
        headers=catalog_context.headers(),
        json={"private_barcode": local_barcode},
    )
    assert adopted_patch.status_code == 409

    second_local = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Local Patch Source {suffix}",
            "private_barcode": _barcode(),
            "private_package_size": "2 l",
        },
    )
    assert second_local.status_code == 201, second_local.text
    local_patch = await catalog_context.client.patch(
        f"/api/catalog/my-products/{second_local.json()['id']}",
        headers=catalog_context.headers(),
        json={"private_barcode": global_barcode},
    )
    assert local_patch.status_code == 409

    link_collision_barcode = _barcode()
    first_global = await _seed_product(
        catalog_context,
        name=f"First Link Identity {suffix}",
        barcode=link_collision_barcode,
    )
    second_global = await _seed_product(
        catalog_context,
        name=f"Second Link Identity {suffix}",
        barcode=f"{link_collision_barcode[:4]}-{link_collision_barcode[4:]}",
    )
    first_link_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{first_global}/adopt",
        headers=catalog_context.headers(),
    )
    assert first_link_adoption.status_code == 201, first_link_adoption.text
    link_source = await _seed_market_product(
        catalog_context,
        market_id=catalog_context.market_a_id,
        private_name=f"Unique Link Source {suffix}",
        private_barcode=_barcode(),
    )
    duplicate_link = await catalog_context.client.post(
        f"/api/catalog/my-products/{link_source}/link-global",
        headers=catalog_context.headers(),
        json={"product_id": str(second_global)},
    )
    assert duplicate_link.status_code == 409

    embedded_name = f"Embedded Brand Product {suffix}"
    embedded_global = await _seed_product(
        catalog_context,
        name=embedded_name,
        brand_id=catalog_context.global_brand_id,
        package_size="400 g",
        package_amount=Decimal(400),
        package_unit="g",
    )
    embedded_local = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Ulker {embedded_name}",
            "private_package_size": "400gr",
            "allow_global_match_override": True,
        },
    )
    assert embedded_local.status_code == 201, embedded_local.text
    embedded_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{embedded_global}/adopt",
        headers=catalog_context.headers(),
    )
    assert embedded_adoption.status_code == 409

    product_alias = f"Local Product Alias {suffix}"
    alias_global = await _seed_product(
        catalog_context,
        name=f"Canonical Alias Target {suffix}",
        package_size="2 l",
        package_amount=Decimal(2),
        package_unit="l",
    )
    async with catalog_context.session_factory() as session:
        session.add(
            ProductAlias(
                product_id=alias_global,
                alias=product_alias,
                normalized_alias=normalize_alias(product_alias),
            )
        )
        await session.commit()
    alias_local = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": product_alias,
            "private_package_size": "2 litre",
            "allow_global_match_override": True,
        },
    )
    assert alias_local.status_code == 201, alias_local.text
    alias_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{alias_global}/adopt",
        headers=catalog_context.headers(),
    )
    assert alias_adoption.status_code == 409

    legacy_alias = f"Linked Legacy Alias {suffix}"
    legacy_alias_global = await _seed_product(
        catalog_context,
        name=f"Global Legacy Canonical {suffix}",
        package_size="1 kg",
        package_amount=Decimal(1),
        package_unit="kg",
    )
    legacy_alias_local = await _seed_product(
        catalog_context,
        name=f"Local Legacy Canonical {suffix}",
        package_size="1000 g",
        package_amount=Decimal(1000),
        package_unit="g",
        is_global=False,
        market_id=catalog_context.market_a_id,
    )
    async with catalog_context.session_factory() as session:
        session.add_all(
            [
                ProductAlias(
                    product_id=legacy_alias_global,
                    alias=legacy_alias,
                    normalized_alias=normalize_alias(legacy_alias),
                ),
                ProductAlias(
                    product_id=legacy_alias_local,
                    alias=legacy_alias,
                    normalized_alias=normalize_alias(legacy_alias),
                ),
            ]
        )
        await session.commit()
    await _seed_market_product(
        catalog_context,
        market_id=catalog_context.market_a_id,
        private_name=f"Different Legacy Display {suffix}",
        legacy_product_id=legacy_alias_local,
    )
    legacy_alias_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{legacy_alias_global}/adopt",
        headers=catalog_context.headers(),
    )
    assert legacy_alias_adoption.status_code == 409

    canonical_brand_id = uuid4()
    async with catalog_context.session_factory() as session:
        canonical_brand = Brand(
            id=canonical_brand_id,
            name=f"Canonical Beverage Brand {suffix}",
            slug=f"canonical-beverage-{suffix}",
            is_global=True,
            market_id=None,
            is_active=True,
        )
        canonical_brand.aliases = [
            BrandAlias(
                alias=f"CBB {suffix}",
                normalized_alias=normalize_alias(f"CBB {suffix}"),
            )
        ]
        session.add(canonical_brand)
        await session.commit()
    brand_alias_name = f"Brand Alias Target {suffix}"
    brand_alias_global = await _seed_product(
        catalog_context,
        name=brand_alias_name,
        brand_id=canonical_brand_id,
        package_size="500 ml",
        package_amount=Decimal(500),
        package_unit="ml",
    )
    brand_alias_local = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": brand_alias_name,
            "private_brand_text": f"CBB {suffix}",
            "private_package_size": "500ml",
            "allow_global_match_override": True,
        },
    )
    assert brand_alias_local.status_code == 201, brand_alias_local.text
    brand_alias_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{brand_alias_global}/adopt",
        headers=catalog_context.headers(),
    )
    assert brand_alias_adoption.status_code == 409


@pytest.mark.asyncio(loop_scope="module")
async def test_legacy_patch_serializes_identity_and_preserves_inactive_references(
    catalog_context: CatalogContext,
) -> None:
    suffix = uuid4().hex[:8]
    target_name = f"Legacy Patch Target {suffix}"
    source_id = await _seed_product(
        catalog_context,
        name=f"Legacy Patch Source {suffix}",
        brand_id=catalog_context.global_brand_id,
        package_size="100 g",
        package_amount=Decimal(100),
        package_unit="g",
        is_global=False,
        market_id=catalog_context.market_a_id,
    )
    await _seed_product(
        catalog_context,
        name=target_name,
        brand_id=catalog_context.global_brand_id,
        package_size="200 g",
        package_amount=Decimal(200),
        package_unit="g",
        is_global=False,
        market_id=catalog_context.market_a_id,
    )
    name_patch, package_patch = await asyncio.gather(
        catalog_context.client.patch(
            f"/api/catalog/products/{source_id}",
            headers=catalog_context.headers(),
            json={"name": target_name},
        ),
        catalog_context.client.patch(
            f"/api/catalog/products/{source_id}",
            headers=catalog_context.headers(),
            json={"package_size": "200 g"},
        ),
    )
    assert sorted((name_patch.status_code, package_patch.status_code)) == [200, 409]

    inactive_brand_id, inactive_category_id = uuid4(), uuid4()
    inactive_legacy_id, legacy_row_id = uuid4(), uuid4()
    async with catalog_context.session_factory() as session:
        session.add_all(
            [
                Brand(
                    id=inactive_brand_id,
                    name=f"Inactive Brand {suffix}",
                    slug=f"inactive-brand-{suffix}",
                    is_global=False,
                    market_id=catalog_context.market_a_id,
                    is_active=False,
                ),
                Category(
                    id=inactive_category_id,
                    name=f"Inactive Category {suffix}",
                    slug=f"inactive-category-{suffix}",
                    is_global=False,
                    market_id=catalog_context.market_a_id,
                    is_active=False,
                ),
            ]
        )
        await session.flush()
        session.add(
            Product(
                id=inactive_legacy_id,
                name=f"Inactive Reference Product {suffix}",
                brand_id=inactive_brand_id,
                category_id=inactive_category_id,
                package_size="100 g",
                package_amount=Decimal(100),
                package_unit="g",
                is_global=False,
                market_id=catalog_context.market_a_id,
                is_active=True,
            )
        )
        await session.flush()
        session.add(
            MarketProduct(
                id=legacy_row_id,
                market_id=catalog_context.market_a_id,
                legacy_product_id=inactive_legacy_id,
                private_name=f"Inactive Reference Product {suffix}",
                category_override_id=inactive_category_id,
            )
        )
        await session.commit()

    unrelated_patch = await catalog_context.client.patch(
        f"/api/catalog/products/{inactive_legacy_id}",
        headers=catalog_context.headers(),
        json={"regular_price": "4.50"},
    )
    assert unrelated_patch.status_code == 200, unrelated_patch.text

    async with catalog_context.session_factory() as session:
        visible = await validate_visible_market_product(
            session,
            legacy_row_id,
            catalog_context.market_a_id,
        )
        resolved = resolved_market_product(visible)
        assert resolved["product_id"] == inactive_legacy_id
        assert resolved["category"] == f"Inactive Category {suffix}"

    link_target = await _seed_product(
        catalog_context,
        name=f"Inactive Category Link Target {suffix}",
        barcode=_barcode(),
    )
    link_with_inactive_category = await catalog_context.client.post(
        f"/api/catalog/my-products/{legacy_row_id}/link-global",
        headers=catalog_context.headers(),
        json={"product_id": str(link_target)},
    )
    assert link_with_inactive_category.status_code == 200, link_with_inactive_category.text

    image_global_id = await _seed_product(
        catalog_context,
        name=f"Legacy URL Image {suffix}",
        barcode=_barcode(),
    )
    image_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{image_global_id}/adopt",
        headers=catalog_context.headers(),
    )
    assert image_adoption.status_code == 201, image_adoption.text
    async with catalog_context.session_factory() as session:
        image_row = await session.get(MarketProduct, UUID(image_adoption.json()["id"]))
        assert image_row is not None
        image_row.image_url = "https://example.test/market-override.png"
        await session.commit()
    image_listing = await catalog_context.client.get(
        "/api/catalog/my-products",
        headers=catalog_context.headers(),
    )
    image_item = next(
        item
        for item in image_listing.json()["items"]
        if item["global_product_id"] == str(image_global_id)
    )
    assert image_item["source_state"] == "global_override"
    assert image_item["image_override_active"] is True
    assert image_item["image_url"] == "https://example.test/market-override.png"


@pytest.mark.asyncio(loop_scope="module")
async def test_private_duplicate_barcode_and_identity_are_blocked_but_size_variant_is_allowed(
    catalog_context: CatalogContext,
) -> None:
    suffix = uuid4().hex[:8]
    barcode = _barcode()
    first = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Lane D Local Biscuit {suffix}",
            "private_brand_text": "Local Brand",
            "private_barcode": barcode,
            "private_package_size": "400gr",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["source_state"] == "local"
    assert first.json()["global_product_id"] is None

    duplicate_barcode = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Different Name {suffix}",
            "private_brand_text": "Other Brand",
            "private_barcode": f"{barcode[:3]}-{barcode[3:8]} {barcode[8:]}",
            "private_package_size": "1 l",
        },
    )
    assert duplicate_barcode.status_code == 409

    duplicate_identity = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"lane d local biscuit {suffix}",
            "private_brand_text": "local brand",
            "package_amount": "400",
            "package_unit": "g",
        },
    )
    assert duplicate_identity.status_code == 409

    legitimate_variant = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Lane D Local Biscuit {suffix}",
            "private_brand_text": "Local Brand",
            "private_package_size": "750 g",
        },
    )
    assert legitimate_variant.status_code == 201, legitimate_variant.text

    different_barcode_variant = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Lane D Local Biscuit {suffix}",
            "private_brand_text": "Local Brand",
            "private_barcode": _barcode(),
            "private_package_size": "400 g",
        },
    )
    assert different_barcode_variant.status_code == 201, different_barcode_variant.text

    display_override_create = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Unique Storage Name {suffix}",
            "display_name_override": f"lane d local biscuit {suffix}",
            "private_brand_text": "local brand",
            "private_package_size": "400 g",
        },
    )
    assert display_override_create.status_code == 409

    patch_source = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={
            "private_name": f"Patch Source {suffix}",
            "private_brand_text": "Local Brand",
            "private_package_size": "400 g",
        },
    )
    assert patch_source.status_code == 201, patch_source.text
    display_override_patch = await catalog_context.client.patch(
        f"/api/catalog/my-products/{patch_source.json()['id']}",
        headers=catalog_context.headers(),
        json={"display_name_override": f"Lane D Local Biscuit {suffix}"},
    )
    assert display_override_patch.status_code == 409


@pytest.mark.asyncio(loop_scope="module")
async def test_private_creation_rechecks_global_match_and_requires_explicit_local_decision(
    catalog_context: CatalogContext,
) -> None:
    name = f"Mutation Recheck Wafer {uuid4().hex[:8]}"
    product_id = await _seed_product(
        catalog_context,
        name=name,
        brand_id=catalog_context.global_brand_id,
        package_size="200 g",
        package_amount=Decimal(200),
        package_unit="g",
    )
    body = {
        "private_name": name.lower(),
        "private_brand_text": "ulker",
        "private_package_size": "200gr",
    }

    # No preliminary /products/match request is made here.
    blocked = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json=body,
    )
    assert blocked.status_code == 409

    explicit_local = await catalog_context.client.post(
        "/api/catalog/private-products",
        headers=catalog_context.headers(),
        json={**body, "allow_global_match_override": True},
    )
    assert explicit_local.status_code == 201, explicit_local.text
    assert explicit_local.json()["source_state"] == "local"
    assert explicit_local.json()["global_product_id"] is None
    async with catalog_context.session_factory() as session:
        adopted_count = await session.scalar(
            select(func.count(MarketProduct.id)).where(
                MarketProduct.market_id == catalog_context.market_a_id,
                MarketProduct.product_id == product_id,
            )
        )
    assert adopted_count == 0


@pytest.mark.asyncio(loop_scope="module")
async def test_match_and_identity_mutations_do_not_cross_tenant_boundaries(
    catalog_context: CatalogContext,
) -> None:
    private_barcode = _barcode()
    private_product_id = await _seed_product(
        catalog_context,
        name=f"Market B Private Secret {uuid4().hex[:8]}",
        barcode=private_barcode,
        brand_id=catalog_context.local_brand_b_id,
        package_size="400 g",
        package_amount=Decimal(400),
        package_unit="g",
        is_global=False,
        market_id=catalog_context.market_b_id,
    )
    invisible = await _match(
        catalog_context,
        {
            "name": "Market B Private Secret",
            "barcode": private_barcode,
            "brand": "Market B Gizli Marka",
            "package_size": "400 g",
        },
    )
    assert invisible.status_code == 200, invisible.text
    assert invisible.json()["match_type"] == "none"
    assert invisible.json()["candidates"] == []

    foreign_brand = await _match(
        catalog_context,
        {
            "name": "Market B Private Secret",
            "brand_id": str(catalog_context.local_brand_b_id),
            "package_size": "400 g",
        },
    )
    assert foreign_brand.status_code == 404

    global_name = f"Shared Without B Override {uuid4().hex[:8]}"
    global_id = await _seed_product(
        catalog_context,
        name=global_name,
        barcode=_barcode(),
        brand_id=catalog_context.global_brand_id,
        package_size="1 l",
        package_amount=Decimal(1),
        package_unit="l",
    )
    market_b_row_id = await _seed_market_product(
        catalog_context,
        market_id=catalog_context.market_b_id,
        product_id=global_id,
        display_name_override="MARKET B SECRET OVERRIDE",
        private_brand_text="MARKET B SECRET BRAND",
        regular_price=Decimal("1.23"),
    )
    global_match = await _match(
        catalog_context,
        {"name": global_name, "brand": "Ulker", "package_size": "1 litre"},
    )
    assert global_match.status_code == 200, global_match.text
    serialized = global_match.text
    assert "MARKET B SECRET" not in serialized
    assert global_match.json()["candidates"][0]["already_adopted"] is False

    cross_adopt = await catalog_context.client.post(
        f"/api/catalog/shared/{private_product_id}/adopt",
        headers=catalog_context.headers(),
    )
    assert cross_adopt.status_code == 404

    malformed_id = await _seed_market_product(
        catalog_context,
        market_id=catalog_context.market_a_id,
        product_id=private_product_id,
        private_name="Safe local fallback",
    )
    listing = await catalog_context.client.get(
        "/api/catalog/my-products",
        headers=catalog_context.headers(),
    )
    assert listing.status_code == 200, listing.text
    assert malformed_id not in {UUID(item["id"]) for item in listing.json()["items"]}
    malformed_patch = await catalog_context.client.patch(
        f"/api/catalog/my-products/{malformed_id}",
        headers=catalog_context.headers(),
        json={"stock_note": "must not mutate a malformed association"},
    )
    assert malformed_patch.status_code == 404

    malformed_legacy_id = await _seed_market_product(
        catalog_context,
        market_id=catalog_context.market_a_id,
        private_name="Safe legacy fallback",
        legacy_product_id=private_product_id,
    )
    legacy_listing = await catalog_context.client.get(
        "/api/catalog/my-products",
        headers=catalog_context.headers(),
    )
    assert legacy_listing.status_code == 200, legacy_listing.text
    malformed_legacy = next(
        item for item in legacy_listing.json()["items"] if item["id"] == str(malformed_legacy_id)
    )
    assert malformed_legacy["product_id"] is None
    assert "Market B Private Secret" not in str(malformed_legacy)
    malformed_legacy_link = await catalog_context.client.post(
        f"/api/catalog/my-products/{malformed_legacy_id}/link-global",
        headers=catalog_context.headers(),
        json={"product_id": str(global_id)},
    )
    assert malformed_legacy_link.status_code == 404

    own_local_id = await _seed_market_product(
        catalog_context,
        market_id=catalog_context.market_a_id,
        private_name=f"Market A Link Source {uuid4().hex[:8]}",
    )
    foreign_target = await catalog_context.client.post(
        f"/api/catalog/my-products/{own_local_id}/link-global",
        headers=catalog_context.headers(),
        json={"product_id": str(private_product_id)},
    )
    assert foreign_target.status_code == 404
    async with catalog_context.session_factory() as session:
        own_local = await session.get(MarketProduct, own_local_id)
        assert own_local is not None and own_local.product_id is None

    cross_link = await catalog_context.client.post(
        f"/api/catalog/my-products/{market_b_row_id}/link-global",
        headers=catalog_context.headers(),
        json={"product_id": str(global_id)},
    )
    assert cross_link.status_code == 404

    own_adoption = await catalog_context.client.post(
        f"/api/catalog/shared/{global_id}/adopt",
        headers=catalog_context.headers(),
    )
    assert own_adoption.status_code == 201, own_adoption.text
    after_adoption = await _match(
        catalog_context,
        {"name": global_name, "brand": "Ulker", "package_size": "1 l"},
    )
    assert after_adoption.json()["candidates"][0]["already_adopted"] is True


@pytest.mark.asyncio(loop_scope="module")
async def test_link_preserves_local_metadata_and_rejects_an_already_adopted_target(
    catalog_context: CatalogContext,
) -> None:
    global_id = await _seed_product(
        catalog_context,
        name=f"Link Target {uuid4().hex[:8]}",
        barcode=_barcode(),
        brand_id=catalog_context.global_brand_id,
        package_size="500 g",
        package_amount=Decimal(500),
        package_unit="g",
        regular_price=Decimal("10.00"),
        badge_text="Global badge",
    )
    local_id = await _seed_market_product(
        catalog_context,
        market_id=catalog_context.market_a_id,
        private_name="Preserved Local Display",
        private_brand_text="Preserved Local Brand",
        private_barcode=_barcode(),
        private_package_size="450 g",
        regular_price=Decimal("12.50"),
        promo_price=Decimal("11.00"),
        badge_text="Local badge",
        stock_note="Local stock",
        image_storage_key="markets/test/preserved.png",
        image_mime_type="image/png",
    )
    linked = await catalog_context.client.post(
        f"/api/catalog/my-products/{local_id}/link-global",
        headers=catalog_context.headers(),
        json={"product_id": str(global_id)},
    )
    assert linked.status_code == 200, linked.text
    payload = linked.json()
    assert payload["id"] == str(local_id)
    assert payload["global_product_id"] == str(global_id)
    assert payload["source_state"] == "global_override"
    assert payload["name"] == "Preserved Local Display"
    assert payload["regular_price"] == "12.50"
    assert payload["image_override_active"] is True
    assert payload["inherited_values"]["name"].startswith("Link Target")

    repeated_link = await catalog_context.client.post(
        f"/api/catalog/my-products/{local_id}/link-global",
        headers=catalog_context.headers(),
        json={"product_id": str(global_id)},
    )
    assert repeated_link.status_code == 409

    async with catalog_context.session_factory() as session:
        row = await session.get(MarketProduct, local_id)
        assert row is not None
        assert row.product_id == global_id
        assert row.private_brand_text == "Preserved Local Brand"
        assert row.private_package_size == "450 g"
        assert row.regular_price == Decimal("12.50")
        assert row.badge_text == "Local badge"
        assert row.image_storage_key == "markets/test/preserved.png"

    second_local_id = await _seed_market_product(
        catalog_context,
        market_id=catalog_context.market_a_id,
        private_name=f"Duplicate Link Source {uuid4().hex[:6]}",
    )
    duplicate = await catalog_context.client.post(
        f"/api/catalog/my-products/{second_local_id}/link-global",
        headers=catalog_context.headers(),
        json={"product_id": str(global_id)},
    )
    assert duplicate.status_code == 409
    async with catalog_context.session_factory() as session:
        untouched = await session.get(MarketProduct, second_local_id)
        assert untouched is not None and untouched.product_id is None


@pytest.mark.asyncio(loop_scope="module")
async def test_global_updates_resolve_live_while_overrides_and_patch_semantics_survive(
    catalog_context: CatalogContext,
) -> None:
    suffix = uuid4().hex[:8]
    global_id = await _seed_product(
        catalog_context,
        name=f"Global Before {suffix}",
        brand_id=catalog_context.global_brand_id,
        package_size="1 l",
        package_amount=Decimal(1),
        package_unit="l",
        regular_price=Decimal("10.00"),
        badge_text="Global before badge",
    )
    adopted = await catalog_context.client.post(
        f"/api/catalog/shared/{global_id}/adopt",
        headers=catalog_context.headers(),
        json={
            "product_id": str(global_id),
            "display_name_override": f"Market Name {suffix}",
            "private_package_size": "900 ml",
            "regular_price": "12.50",
            "badge_text": "Market badge",
            "currency": "EUR",
        },
    )
    assert adopted.status_code == 201, adopted.text
    market_product_id = adopted.json()["id"]

    async with catalog_context.session_factory() as session:
        product = await session.get(Product, global_id)
        assert product is not None
        product.name = f"Global After {suffix}"
        product.package_size = "2 l"
        product.package_amount = Decimal(2)
        product.package_unit = "l"
        product.regular_price = Decimal("20.00")
        product.badge_text = "Global after badge"
        await session.commit()

    listing = await catalog_context.client.get(
        "/api/catalog/my-products",
        headers=catalog_context.headers(),
    )
    assert listing.status_code == 200, listing.text
    item = next(
        row for row in listing.json()["items"] if row["global_product_id"] == str(global_id)
    )
    assert item["source_state"] == "global_override"
    assert item["name"] == f"Market Name {suffix}"
    assert item["package_size"] == "900 ml"
    assert item["regular_price"] == "12.50"
    assert item["inherited_values"]["name"] == f"Global After {suffix}"
    assert item["inherited_values"]["package_size"] == "2 l"
    assert item["inherited_values"]["regular_price"] == "20.00"
    assert item["override_values"]["regular_price"] == "12.50"

    omitted_patch = await catalog_context.client.patch(
        f"/api/catalog/my-products/{market_product_id}",
        headers=catalog_context.headers(),
        json={"stock_note": "Only this field changes"},
    )
    assert omitted_patch.status_code == 200, omitted_patch.text
    assert omitted_patch.json()["name"] == f"Market Name {suffix}"
    assert omitted_patch.json()["package_size"] == "900 ml"
    assert omitted_patch.json()["regular_price"] == "12.50"

    cleared = await catalog_context.client.patch(
        f"/api/catalog/my-products/{market_product_id}",
        headers=catalog_context.headers(),
        json={
            "display_name_override": None,
            "private_package_size": None,
            "regular_price": None,
        },
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["name"] == f"Global After {suffix}"
    assert cleared.json()["package_size"] == "2 l"
    assert cleared.json()["regular_price"] == "20.00"

    partial_package = await catalog_context.client.patch(
        f"/api/catalog/my-products/{market_product_id}",
        headers=catalog_context.headers(),
        json={"package_unit": "ml"},
    )
    assert partial_package.status_code == 422

    after_partial = await catalog_context.client.get(
        "/api/catalog/my-products",
        headers=catalog_context.headers(),
    )
    unchanged = next(
        row for row in after_partial.json()["items"] if row["global_product_id"] == str(global_id)
    )
    assert unchanged["package_amount"] == "2.000"
    assert unchanged["package_unit"] == "l"
