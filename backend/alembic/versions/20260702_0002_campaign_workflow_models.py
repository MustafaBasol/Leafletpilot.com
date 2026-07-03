"""campaign workflow models

Revision ID: 20260702_0002
Revises: 20260702_0001
Create Date: 2026-07-02 00:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260702_0002"
down_revision: str | None = "20260702_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("raw_input_text", sa.Text(), nullable=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("campaign_start_date", sa.Date(), nullable=True),
        sa.Column("campaign_end_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("product_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("low_confidence_count", sa.Integer(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel is null or channel in ('panel', 'telegram', 'whatsapp', 'import')",
            name="ck_campaigns_channel",
        ),
        sa.CheckConstraint(
            "source_type is null or source_type in ('text', 'excel', 'pdf', 'barcode_list', 'manual')",
            name="ck_campaigns_source_type",
        ),
        sa.CheckConstraint(
            "status in ("
            "'draft', 'parsing', 'matching', 'missing_products', 'preview_ready', "
            "'waiting_approval', 'revision_requested', 'approved', 'generating_files', "
            "'completed', 'failed', 'cancelled')",
            name="ck_campaigns_status",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaigns_channel", "campaigns", ["channel"])
    op.create_index("ix_campaigns_created_at", "campaigns", ["created_at"])
    op.create_index("ix_campaigns_market_id", "campaigns", ["market_id"])
    op.create_index("ix_campaigns_slug", "campaigns", ["slug"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])
    op.create_index("ix_campaigns_updated_at", "campaigns", ["updated_at"])

    op.create_table(
        "campaign_files",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=1000), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("sent_to_user_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "file_type in ("
            "'preview_png', 'brochure_pdf', 'brochure_png', 'instagram_post', "
            "'instagram_story', 'whatsapp_image', 'source_upload')",
            name="ck_campaign_files_file_type",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'generating', 'ready', 'failed', 'sent')",
            name="ck_campaign_files_status",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_files_campaign_id", "campaign_files", ["campaign_id"])
    op.create_index("ix_campaign_files_created_at", "campaign_files", ["created_at"])
    op.create_index("ix_campaign_files_file_type", "campaign_files", ["file_type"])
    op.create_index("ix_campaign_files_market_id", "campaign_files", ["market_id"])
    op.create_index("ix_campaign_files_status", "campaign_files", ["status"])

    op.create_table(
        "campaign_items",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_line", sa.Text(), nullable=False),
        sa.Column("incoming_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("old_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("unit_label", sa.String(length=64), nullable=True),
        sa.Column("quantity_label", sa.String(length=64), nullable=True),
        sa.Column("category_hint", sa.String(length=120), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_hero", sa.Boolean(), nullable=False),
        sa.Column("match_status", sa.String(length=32), nullable=False),
        sa.Column("match_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("matching_notes", sa.Text(), nullable=True),
        sa.Column("parsed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "match_status in ("
            "'matched', 'low_confidence', 'not_found', 'manual_selected', "
            "'new_product_needed', 'use_without_image', 'excluded')",
            name="ck_campaign_items_match_status",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_items_campaign_id", "campaign_items", ["campaign_id"])
    op.create_index("ix_campaign_items_market_id", "campaign_items", ["market_id"])
    op.create_index("ix_campaign_items_match_status", "campaign_items", ["match_status"])
    op.create_index("ix_campaign_items_normalized_name", "campaign_items", ["normalized_name"])
    op.create_index("ix_campaign_items_product_id", "campaign_items", ["product_id"])
    op.create_index("ix_campaign_items_sort_order", "campaign_items", ["sort_order"])

    op.create_table(
        "conversations",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_chat_id", sa.String(length=255), nullable=True),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("current_state", sa.String(length=64), nullable=False),
        sa.Column("state_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider in ('telegram', 'whatsapp', 'panel')",
            name="ck_conversations_provider",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_current_state", "conversations", ["current_state"])
    op.create_index("ix_conversations_external_chat_id", "conversations", ["external_chat_id"])
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])
    op.create_index("ix_conversations_market_id", "conversations", ["market_id"])
    op.create_index("ix_conversations_provider", "conversations", ["provider"])
    op.create_index(
        "uq_conversations_market_provider_external_chat_id",
        "conversations",
        ["market_id", "provider", "external_chat_id"],
        unique=True,
        postgresql_where=sa.text("external_chat_id IS NOT NULL"),
    )

    op.create_table(
        "export_jobs",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_formats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_file_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "job_type in ('preview', 'final_export', 'regenerate_preview', 'send_files')",
            name="ck_export_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status in ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_export_jobs_status",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_jobs_campaign_id", "export_jobs", ["campaign_id"])
    op.create_index("ix_export_jobs_created_at", "export_jobs", ["created_at"])
    op.create_index("ix_export_jobs_job_type", "export_jobs", ["job_type"])
    op.create_index("ix_export_jobs_market_id", "export_jobs", ["market_id"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])

    op.create_table(
        "incoming_messages",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_mime_type", sa.String(length=100), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_key", sa.String(length=1000), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "direction in ('inbound', 'outbound')",
            name="ck_incoming_messages_direction",
        ),
        sa.CheckConstraint(
            "message_type in ('text', 'file', 'image', 'button', 'system')",
            name="ck_incoming_messages_message_type",
        ),
        sa.CheckConstraint(
            "provider in ('telegram', 'whatsapp', 'panel')",
            name="ck_incoming_messages_provider",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incoming_messages_campaign_id", "incoming_messages", ["campaign_id"])
    op.create_index("ix_incoming_messages_conversation_id", "incoming_messages", ["conversation_id"])
    op.create_index("ix_incoming_messages_created_at", "incoming_messages", ["created_at"])
    op.create_index(
        "ix_incoming_messages_external_message_id",
        "incoming_messages",
        ["external_message_id"],
    )
    op.create_index("ix_incoming_messages_market_id", "incoming_messages", ["market_id"])
    op.create_index("ix_incoming_messages_provider", "incoming_messages", ["provider"])

    op.create_table(
        "matching_suggestions",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("suggested_name", sa.String(length=255), nullable=True),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason is null or reason in ('exact', 'alias', 'barcode', 'fuzzy', 'ai_normalized', 'manual')",
            name="ck_matching_suggestions_reason",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["campaign_item_id"], ["campaign_items.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matching_suggestions_campaign_id", "matching_suggestions", ["campaign_id"])
    op.create_index(
        "ix_matching_suggestions_campaign_item_id",
        "matching_suggestions",
        ["campaign_item_id"],
    )
    op.create_index("ix_matching_suggestions_market_id", "matching_suggestions", ["market_id"])
    op.create_index("ix_matching_suggestions_product_id", "matching_suggestions", ["product_id"])
    op.create_index("ix_matching_suggestions_rank", "matching_suggestions", ["rank"])
    op.create_index("ix_matching_suggestions_score", "matching_suggestions", ["score"])


def downgrade() -> None:
    op.drop_index("ix_matching_suggestions_score", table_name="matching_suggestions")
    op.drop_index("ix_matching_suggestions_rank", table_name="matching_suggestions")
    op.drop_index("ix_matching_suggestions_product_id", table_name="matching_suggestions")
    op.drop_index("ix_matching_suggestions_market_id", table_name="matching_suggestions")
    op.drop_index("ix_matching_suggestions_campaign_item_id", table_name="matching_suggestions")
    op.drop_index("ix_matching_suggestions_campaign_id", table_name="matching_suggestions")
    op.drop_table("matching_suggestions")
    op.drop_index("ix_incoming_messages_provider", table_name="incoming_messages")
    op.drop_index("ix_incoming_messages_market_id", table_name="incoming_messages")
    op.drop_index("ix_incoming_messages_external_message_id", table_name="incoming_messages")
    op.drop_index("ix_incoming_messages_created_at", table_name="incoming_messages")
    op.drop_index("ix_incoming_messages_conversation_id", table_name="incoming_messages")
    op.drop_index("ix_incoming_messages_campaign_id", table_name="incoming_messages")
    op.drop_table("incoming_messages")
    op.drop_index("ix_export_jobs_status", table_name="export_jobs")
    op.drop_index("ix_export_jobs_market_id", table_name="export_jobs")
    op.drop_index("ix_export_jobs_job_type", table_name="export_jobs")
    op.drop_index("ix_export_jobs_created_at", table_name="export_jobs")
    op.drop_index("ix_export_jobs_campaign_id", table_name="export_jobs")
    op.drop_table("export_jobs")
    op.drop_index(
        "uq_conversations_market_provider_external_chat_id",
        table_name="conversations",
        postgresql_where=sa.text("external_chat_id IS NOT NULL"),
    )
    op.drop_index("ix_conversations_provider", table_name="conversations")
    op.drop_index("ix_conversations_market_id", table_name="conversations")
    op.drop_index("ix_conversations_last_message_at", table_name="conversations")
    op.drop_index("ix_conversations_external_chat_id", table_name="conversations")
    op.drop_index("ix_conversations_current_state", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_campaign_items_sort_order", table_name="campaign_items")
    op.drop_index("ix_campaign_items_product_id", table_name="campaign_items")
    op.drop_index("ix_campaign_items_normalized_name", table_name="campaign_items")
    op.drop_index("ix_campaign_items_match_status", table_name="campaign_items")
    op.drop_index("ix_campaign_items_market_id", table_name="campaign_items")
    op.drop_index("ix_campaign_items_campaign_id", table_name="campaign_items")
    op.drop_table("campaign_items")
    op.drop_index("ix_campaign_files_status", table_name="campaign_files")
    op.drop_index("ix_campaign_files_market_id", table_name="campaign_files")
    op.drop_index("ix_campaign_files_file_type", table_name="campaign_files")
    op.drop_index("ix_campaign_files_created_at", table_name="campaign_files")
    op.drop_index("ix_campaign_files_campaign_id", table_name="campaign_files")
    op.drop_table("campaign_files")
    op.drop_index("ix_campaigns_updated_at", table_name="campaigns")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_index("ix_campaigns_slug", table_name="campaigns")
    op.drop_index("ix_campaigns_market_id", table_name="campaigns")
    op.drop_index("ix_campaigns_created_at", table_name="campaigns")
    op.drop_index("ix_campaigns_channel", table_name="campaigns")
    op.drop_table("campaigns")
