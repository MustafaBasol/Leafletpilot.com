from pathlib import Path
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Numeric, UniqueConstraint

import app.models
from app.core.config import settings
from app.core.database import Base
from app.models import (
    Campaign,
    CampaignFile,
    CampaignItem,
    Conversation,
    ExportJob,
    IncomingMessage,
    Market,
    MatchingSuggestion,
    Product,
    ProductAlias,
    TelegramAccount,
    TelegramConversationState,
    TelegramUpdate,
    User,
)


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
    "campaigns",
    "campaign_items",
    "campaign_files",
    "matching_suggestions",
    "export_jobs",
    "conversations",
    "incoming_messages",
    "telegram_accounts",
    "telegram_updates",
    "telegram_conversation_states",
}


def test_models_are_imported_into_metadata() -> None:
    assert app.models.User is User
    assert EXPECTED_TABLES.issubset(Base.metadata.tables)


def test_representative_model_constructors_work() -> None:
    user = User(email="owner@example.com", full_name="Owner")
    market = Market(name="Demo Market", slug="demo-market")
    product = Product(name="Milk 1L", is_global=True)
    alias = ProductAlias(alias="sut 1l", normalized_alias="sut 1l", product=product)
    campaign = Campaign(title="Week 28 Deals", market=market, created_by_user=user)
    campaign_item = CampaignItem(
        campaign=campaign,
        market=market,
        raw_line="Milk 1L - 1.29",
        incoming_name="Milk 1L",
        price=Decimal("1.29"),
    )
    campaign_file = CampaignFile(
        campaign=campaign,
        market=market,
        file_type="preview_png",
        format="png",
    )
    suggestion = MatchingSuggestion(
        campaign=campaign,
        campaign_item=campaign_item,
        market=market,
        product=product,
        score=Decimal("94.50"),
        reason="alias",
    )
    export_job = ExportJob(
        campaign=campaign,
        market=market,
        requested_by_user=user,
        job_type="preview",
    )
    conversation = Conversation(market=market, campaign=campaign, provider="telegram")
    incoming_message = IncomingMessage(
        market=market,
        conversation=conversation,
        campaign=campaign,
        provider="telegram",
        message_type="text",
        text="Milk 1L - 1.29",
    )
    telegram_account = TelegramAccount(user=user, telegram_user_id=123456789)
    telegram_update = TelegramUpdate(update_id=1001, status="received", telegram_user_id=123456789)
    telegram_state = TelegramConversationState(
        telegram_account=telegram_account,
        user=user,
        telegram_user_id=123456789,
        chat_id=123456789,
        selected_market=market,
    )

    assert user.email == "owner@example.com"
    assert market.currency is None
    assert product.name == "Milk 1L"
    assert product.aliases == [alias]
    assert campaign.items == [campaign_item]
    assert campaign.files == [campaign_file]
    assert campaign.matching_suggestions == [suggestion]
    assert campaign.export_jobs == [export_job]
    assert campaign.conversation is conversation
    assert conversation.incoming_messages == [incoming_message]
    assert telegram_account.telegram_user_id == 123456789
    assert telegram_update.update_id == 1001
    assert telegram_state.state is None
    assert campaign_item.price == Decimal("1.29")
    assert suggestion.score == Decimal("94.50")


def test_expected_constraints_and_indexes_exist() -> None:
    users = Base.metadata.tables["users"]
    market_users = Base.metadata.tables["market_users"]
    product_aliases = Base.metadata.tables["product_aliases"]
    campaign_items = Base.metadata.tables["campaign_items"]
    campaign_files = Base.metadata.tables["campaign_files"]
    conversations = Base.metadata.tables["conversations"]
    telegram_accounts = Base.metadata.tables["telegram_accounts"]
    telegram_updates = Base.metadata.tables["telegram_updates"]
    telegram_states = Base.metadata.tables["telegram_conversation_states"]

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
    assert "ix_campaign_items_campaign_id" in {index.name for index in campaign_items.indexes}
    assert "ix_campaign_files_campaign_id" in {index.name for index in campaign_files.indexes}
    assert "ix_campaign_files_status" in {index.name for index in campaign_files.indexes}
    assert "ix_conversations_provider" in {index.name for index in conversations.indexes}
    assert "ix_conversations_external_chat_id" in {index.name for index in conversations.indexes}
    assert "ix_telegram_accounts_telegram_user_id" in {index.name for index in telegram_accounts.indexes}
    assert "uq_telegram_accounts_active_user_id" in {index.name for index in telegram_accounts.indexes}
    assert "ix_telegram_updates_update_id" in {index.name for index in telegram_updates.indexes}
    assert "ix_telegram_conversation_states_telegram_user_id" in {index.name for index in telegram_states.indexes}


def test_campaign_decimal_columns_use_numeric_types() -> None:
    campaign_items = Base.metadata.tables["campaign_items"]
    matching_suggestions = Base.metadata.tables["matching_suggestions"]

    assert isinstance(campaign_items.c.price.type, Numeric)
    assert campaign_items.c.price.type.precision == 10
    assert campaign_items.c.price.type.scale == 2
    assert isinstance(campaign_items.c.old_price.type, Numeric)
    assert campaign_items.c.old_price.type.precision == 10
    assert campaign_items.c.old_price.type.scale == 2
    assert isinstance(campaign_items.c.match_confidence.type, Numeric)
    assert campaign_items.c.match_confidence.type.precision == 5
    assert campaign_items.c.match_confidence.type.scale == 2
    assert isinstance(matching_suggestions.c.score.type, Numeric)
    assert matching_suggestions.c.score.type.precision == 5
    assert matching_suggestions.c.score.type.scale == 2


def test_alembic_initial_catalog_migration_exists() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260702_0001_initial_core_catalog_models.py"
    )

    assert migration_path.exists()


def test_alembic_campaign_workflow_migration_exists() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260702_0002_campaign_workflow_models.py"
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
