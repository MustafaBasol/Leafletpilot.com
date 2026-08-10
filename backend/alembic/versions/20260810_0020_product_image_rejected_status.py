"""Allow product images to be marked rejected during platform admin review."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260810_0020"
down_revision: str | None = "20260809_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_product_images_quality_status", "product_images", type_="check")
    op.create_check_constraint(
        "ck_product_images_quality_status",
        "product_images",
        "quality_status in ('excellent', 'good', 'needs_review', 'missing', 'rejected')",
    )


def downgrade() -> None:
    op.execute("UPDATE product_images SET quality_status = 'needs_review' WHERE quality_status = 'rejected'")
    op.drop_constraint("ck_product_images_quality_status", "product_images", type_="check")
    op.create_check_constraint(
        "ck_product_images_quality_status",
        "product_images",
        "quality_status in ('excellent', 'good', 'needs_review', 'missing')",
    )
