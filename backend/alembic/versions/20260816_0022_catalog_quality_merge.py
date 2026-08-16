"""Add global catalog merge tombstones and quality decisions."""

import sqlalchemy as sa
from alembic import op


revision = "20260816_0022"
down_revision = "20260815_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "merged_into_product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", name="fk_products_merged_into_product_id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_products_merged_into_product_id",
        "products",
        ["merged_into_product_id"],
    )
    op.create_check_constraint(
        "ck_products_merged_not_self",
        "products",
        "merged_into_product_id is null or merged_into_product_id <> id",
    )

    op.create_table(
        "catalog_quality_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_a_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", name="fk_catalog_quality_decisions_product_a"),
            nullable=False,
        ),
        sa.Column(
            "product_b_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", name="fk_catalog_quality_decisions_product_b"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(32), nullable=False, server_default="ignored"),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column(
            "created_by_platform_admin_id",
            sa.Uuid(),
            sa.ForeignKey(
                "platform_admins.id",
                name="fk_catalog_quality_decisions_created_by_platform_admin",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "product_a_id <> product_b_id",
            name="ck_catalog_quality_decisions_distinct_products",
        ),
        sa.CheckConstraint(
            "product_a_id < product_b_id",
            name="ck_catalog_quality_decisions_ordered_pair",
        ),
        sa.CheckConstraint(
            "decision in ('ignored')",
            name="ck_catalog_quality_decisions_decision",
        ),
        sa.UniqueConstraint(
            "product_a_id",
            "product_b_id",
            name="uq_catalog_quality_decisions_product_pair",
        ),
    )


def downgrade() -> None:
    op.drop_table("catalog_quality_decisions")
    op.drop_constraint("ck_products_merged_not_self", "products", type_="check")
    op.drop_index("ix_products_merged_into_product_id", table_name="products")
    op.drop_constraint(
        "fk_products_merged_into_product_id",
        "products",
        type_="foreignkey",
    )
    op.drop_column("products", "merged_into_product_id")
