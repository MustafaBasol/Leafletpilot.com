"""Professionalization retry lineage and rejected-candidate metadata.

Revision ID: 20260829_0035
Revises: 20260827_0034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260829_0035"
down_revision: str | None = "20260827_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_professionalization_runs",
        sa.Column(
            "source_type", sa.String(length=32), nullable=False, server_default="approved_original"
        ),
    )
    op.add_column(
        "ai_professionalization_runs",
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_professionalization_runs", sa.Column("user_instruction", sa.Text(), nullable=True)
    )
    op.add_column(
        "ai_professionalization_runs",
        sa.Column("candidate_image_storage_key", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "ai_professionalization_runs",
        sa.Column("failure_category", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_professionalization_runs_source_run",
        "ai_professionalization_runs",
        "ai_professionalization_runs",
        ["source_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_professionalization_runs_source_run",
        "ai_professionalization_runs",
        ["source_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_professionalization_runs_source_run", table_name="ai_professionalization_runs"
    )
    op.drop_constraint(
        "fk_ai_professionalization_runs_source_run",
        "ai_professionalization_runs",
        type_="foreignkey",
    )
    for column in (
        "failure_category",
        "candidate_image_storage_key",
        "user_instruction",
        "source_run_id",
        "source_type",
    ):
        op.drop_column("ai_professionalization_runs", column)
