"""Market-level brochure identity and visibility preferences.

Revision ID: 20260827_0034
Revises: 20260827_0033
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_0034"
down_revision: str | None = "20260827_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("markets", sa.Column("address_line_1", sa.String(length=255), nullable=True))
    op.add_column("markets", sa.Column("address_line_2", sa.String(length=255), nullable=True))
    op.add_column("markets", sa.Column("postal_code", sa.String(length=32), nullable=True))
    op.add_column("markets", sa.Column("website_url", sa.String(length=500), nullable=True))
    op.add_column("markets", sa.Column("instagram_url", sa.String(length=500), nullable=True))
    op.add_column("markets", sa.Column("facebook_url", sa.String(length=500), nullable=True))
    op.add_column("markets", sa.Column("brochure_show_logo", sa.Boolean(), nullable=False, server_default=sa.true()))
    for name in ("brochure_show_address", "brochure_show_phone", "brochure_show_website", "brochure_show_instagram", "brochure_show_facebook"):
        op.add_column("markets", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for name in ("brochure_show_facebook", "brochure_show_instagram", "brochure_show_website", "brochure_show_phone", "brochure_show_address", "brochure_show_logo", "facebook_url", "instagram_url", "website_url", "postal_code", "address_line_2", "address_line_1"):
        op.drop_column("markets", name)