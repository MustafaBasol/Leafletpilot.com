"""Automatic final AI brochure images and market logos.

Revision ID: 20260827_0033
Revises: 20260827_0032
"""
from collections.abc import Sequence
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "20260827_0033"
down_revision: str | None = "20260827_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("markets", sa.Column("logo_storage_key", sa.String(length=1000), nullable=True))
    op.add_column("markets", sa.Column("logo_mime_type", sa.String(length=64), nullable=True))
    op.add_column("ai_professionalization_runs", sa.Column("request_mode", sa.String(length=32), nullable=False, server_default="automatic"))
    op.add_column("ai_professionalization_runs", sa.Column("source_image_storage_key", sa.String(length=1000), nullable=True))
    op.add_column("ai_professionalization_runs", sa.Column("logo_storage_key", sa.String(length=1000), nullable=True))
    op.add_column("ai_professionalization_runs", sa.Column("generated_image_storage_key", sa.String(length=1000), nullable=True))
    op.add_column("ai_professionalization_runs", sa.Column("generated_image_file_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_professionalization_runs", sa.Column("generated_pdf_storage_key", sa.String(length=1000), nullable=True))
    op.add_column("ai_professionalization_runs", sa.Column("validation_report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("ai_professionalization_runs", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("ai_professionalization_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("ai_professionalization_runs", "created_by_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_foreign_key("fk_ai_professionalization_runs_generated_image_file", "ai_professionalization_runs", "campaign_files", ["generated_image_file_id"], ["id"])
    op.drop_constraint("ck_ai_professionalization_runs_status", "ai_professionalization_runs", type_="check")
    op.create_check_constraint("ck_ai_professionalization_runs_status", "ai_professionalization_runs", "status in ('pending', 'generating', 'validating', 'ready', 'applied', 'rejected', 'superseded', 'failed')")


def downgrade() -> None:
    op.drop_constraint("ck_ai_professionalization_runs_status", "ai_professionalization_runs", type_="check")
    op.create_check_constraint("ck_ai_professionalization_runs_status", "ai_professionalization_runs", "status in ('ready', 'applied', 'superseded', 'failed')")
    op.drop_constraint("fk_ai_professionalization_runs_generated_image_file", "ai_professionalization_runs", type_="foreignkey")
    for column in ("completed_at", "error_code", "validation_report_json", "generated_pdf_storage_key", "generated_image_file_id", "generated_image_storage_key", "logo_storage_key", "source_image_storage_key", "request_mode"):
        op.drop_column("ai_professionalization_runs", column)
    op.drop_column("markets", "logo_mime_type")
    op.drop_column("markets", "logo_storage_key")