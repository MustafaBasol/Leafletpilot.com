"""Add product promo fields used by the flyer builder."""

from alembic import op
import sqlalchemy as sa

revision = "20260711_0012"
down_revision = "20260711_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("markets", sa.Column("promo_profile_json", sa.JSON(), nullable=True))
    op.add_column("products", sa.Column("regular_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("products", sa.Column("promo_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("products", sa.Column("currency", sa.String(3), server_default="EUR", nullable=False))
    op.add_column("products", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False))
    op.add_column("products", sa.Column("badge_text", sa.String(64), nullable=True))


def downgrade() -> None:
    for name in ("badge_text", "sort_order", "currency", "promo_price", "regular_price"):
        op.drop_column("products", name)
    op.drop_column("markets", "promo_profile_json")
