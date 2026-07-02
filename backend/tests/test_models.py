from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import UniqueConstraint

import app.models
from app.core.config import settings
from app.core.database import Base
from app.models import Market, Product, ProductAlias, User


EXPECTED_TABLES = {
    "users",
    "markets",
    "market_users",
    "brands",
    "categories",
    "products",
    "product_aliases",
    "product_images",
    "activity_logs",
}


def test_models_are_imported_into_metadata() -> None:
    assert app.models.User is User
    assert EXPECTED_TABLES.issubset(Base.metadata.tables)


def test_representative_model_constructors_work() -> None:
    user = User(email="owner@example.com", full_name="Owner")
    market = Market(name="Demo Market", slug="demo-market")
    product = Product(name="Milk 1L", is_global=True)
    alias = ProductAlias(alias="sut 1l", normalized_alias="sut 1l", product=product)

    assert user.email == "owner@example.com"
    assert market.currency is None
    assert product.name == "Milk 1L"
    assert product.aliases == [alias]


def test_expected_constraints_and_indexes_exist() -> None:
    users = Base.metadata.tables["users"]
    market_users = Base.metadata.tables["market_users"]
    product_aliases = Base.metadata.tables["product_aliases"]

    assert users.c.email.unique is True
    assert "ix_users_email" in {index.name for index in users.indexes}
    assert _has_unique_constraint(
        market_users,
        "uq_market_users_market_id_user_id",
        ("market_id", "user_id"),
    )
    assert _has_unique_constraint(
        product_aliases,
        "uq_product_aliases_product_id_normalized_alias",
        ("product_id", "normalized_alias"),
    )


def test_alembic_initial_catalog_migration_exists() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260702_0001_initial_core_catalog_models.py"
    )

    assert migration_path.exists()


@pytest.mark.asyncio
async def test_live_database_url_optional_for_model_phase() -> None:
    if not settings.database_url:
        pytest.skip("DATABASE_URL is not configured; live migration validation is optional.")

    pytest.importorskip("asyncpg")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    except Exception as exc:
        pytest.skip(f"DATABASE_URL is configured but not reachable: {exc}")
    finally:
        await engine.dispose()


def _has_unique_constraint(table, name: str, columns: tuple[str, ...]) -> bool:
    return any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == name
        and tuple(column.name for column in constraint.columns) == columns
        for constraint in table.constraints
    )
