import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts import seed_dev_data


class RelationshipGuard:
    id = uuid4()

    @property
    def aliases(self):
        raise AssertionError("upsert_aliases must not read product.aliases")

    @property
    def images(self):
        raise AssertionError("upsert_product_image must not read product.images")


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, *, alias_rows=None, image_id=None):
        self.alias_rows = alias_rows or []
        self.image_id = image_id
        self.added = []
        self.executed = []
        self.scalar_statements = []
        self.flush_count = 0

    async def execute(self, statement):
        self.executed.append(statement)
        return ScalarRows(self.alias_rows)

    async def scalar(self, statement):
        self.scalar_statements.append(statement)
        return self.image_id

    def add(self, instance):
        self.added.append(instance)

    async def flush(self):
        self.flush_count += 1


def test_seed_script_constants_and_helpers() -> None:
    assert seed_dev_data.DEMO_USER_EMAIL == "demo@leafletpilot.com"
    assert seed_dev_data.DEMO_USER_PASSWORD == "demo1234"
    assert seed_dev_data.DEMO_MARKET_SLUG == "anadolu-market"
    assert seed_dev_data.verify_password(
        seed_dev_data.DEMO_USER_PASSWORD,
        seed_dev_data.hash_password(seed_dev_data.DEMO_USER_PASSWORD),
    )

    barcodes = [product.barcode for product in seed_dev_data.DEMO_PRODUCTS]
    assert len(barcodes) == len(set(barcodes))

    instance = SimpleNamespace(name="Old Name", is_active=True)
    assert seed_dev_data.update_fields(instance, name="Old Name", is_active=True) is False
    assert seed_dev_data.update_fields(instance, name="New Name", is_active=True) is True
    assert instance.name == "New Name"


def test_seed_refuses_production(monkeypatch) -> None:
    monkeypatch.setattr(seed_dev_data.settings, "environment", "production")

    with pytest.raises(RuntimeError, match=seed_dev_data.PRODUCTION_SEED_MESSAGE):
        seed_dev_data.require_seed_allowed()


def test_seed_allows_development(monkeypatch) -> None:
    monkeypatch.setattr(seed_dev_data.settings, "environment", "development")

    seed_dev_data.require_seed_allowed()


def test_seed_product_helpers_do_not_read_lazy_relationships() -> None:
    asyncio.run(_exercise_seed_product_helpers())


async def _exercise_seed_product_helpers() -> None:
    try:
        product = RelationshipGuard()

        alias_session = FakeSession(
            alias_rows=[seed_dev_data.normalize_alias("Existing Alias")]
        )
        alias_counts = {"created": 0, "updated": 0, "unchanged": 0}
        await seed_dev_data.upsert_aliases(
            alias_session,
            product,
            ("Existing Alias", "New Alias"),
            alias_counts,
        )
        assert len(alias_session.executed) == 1
        assert len(alias_session.added) == 1
        assert alias_session.added[0].normalized_alias == seed_dev_data.normalize_alias(
            "New Alias"
        )
        assert alias_counts == {"created": 1, "updated": 0, "unchanged": 1}

        existing_image_session = FakeSession(image_id=uuid4())
        existing_image_counts = {"created": 0, "updated": 0, "unchanged": 0}
        await seed_dev_data.upsert_product_image(
            existing_image_session,
            product,
            seed_dev_data.DEMO_PRODUCTS[0],
            existing_image_counts,
        )
        assert len(existing_image_session.scalar_statements) == 1
        assert existing_image_session.added == []
        assert existing_image_counts == {"created": 0, "updated": 0, "unchanged": 1}

        new_image_session = FakeSession(image_id=None)
        new_image_counts = {"created": 0, "updated": 0, "unchanged": 0}
        await seed_dev_data.upsert_product_image(
            new_image_session,
            product,
            seed_dev_data.DEMO_PRODUCTS[0],
            new_image_counts,
        )
        assert len(new_image_session.scalar_statements) == 1
        assert len(new_image_session.added) == 1
        assert new_image_session.added[0].product_id == product.id
        assert new_image_counts == {"created": 1, "updated": 0, "unchanged": 0}
    finally:
        if seed_dev_data.engine is not None:
            await seed_dev_data.engine.dispose()
