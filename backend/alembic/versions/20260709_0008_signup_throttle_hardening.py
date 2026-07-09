"""signup throttle hardening

Revision ID: 20260709_0008
Revises: 20260709_0007
Create Date: 2026-07-09 00:08:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260709_0008"
down_revision: str | None = "20260709_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_signup_throttles_key_window", table_name="signup_throttles")
    op.execute("DELETE FROM signup_throttles")
    op.add_column("signup_throttles", sa.Column("key_type", sa.String(length=16), nullable=True))
    op.add_column("signup_throttles", sa.Column("window_bucket", sa.Integer(), nullable=True))
    op.execute("UPDATE signup_throttles SET key_type = 'email', window_bucket = 0")
    op.alter_column("signup_throttles", "key_type", existing_type=sa.String(length=16), nullable=False)
    op.alter_column("signup_throttles", "window_bucket", existing_type=sa.Integer(), nullable=False)
    op.create_check_constraint("ck_signup_throttles_key_type", "signup_throttles", "key_type in ('ip', 'email')")
    op.create_unique_constraint(
        "uq_signup_throttles_type_key_bucket",
        "signup_throttles",
        ["key_type", "key_hash", "window_bucket"],
    )
    op.create_index("ix_signup_throttles_bucket", "signup_throttles", ["window_bucket"])


def downgrade() -> None:
    op.drop_index("ix_signup_throttles_bucket", table_name="signup_throttles")
    op.drop_constraint("uq_signup_throttles_type_key_bucket", "signup_throttles", type_="unique")
    op.drop_constraint("ck_signup_throttles_key_type", "signup_throttles", type_="check")
    op.drop_column("signup_throttles", "window_bucket")
    op.drop_column("signup_throttles", "key_type")
    op.create_index("ix_signup_throttles_key_window", "signup_throttles", ["key_hash", "window_started_at"])
