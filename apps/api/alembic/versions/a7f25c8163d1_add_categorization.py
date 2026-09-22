"""Persist receipt categorization state and seed the global taxonomy.

Revision ID: a7f25c8163d1
Revises: 41c1d4a2b0e9
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from shared.taxonomy import DEFAULT_TAXONOMY


revision: str = "a7f25c8163d1"
down_revision: Union[str, Sequence[str], None] = "41c1d4a2b0e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    status = sa.Enum("PENDING", "PROCESSING", "SUCCEEDED", "FAILED", name="extraction_status")
    op.add_column(
        "receipts",
        sa.Column("categorization_status", status, nullable=False, server_default="PENDING"),
    )
    op.add_column("receipts", sa.Column("categorization_error", sa.Text(), nullable=True))
    op.add_column(
        "line_items",
        sa.Column("needs_category_review", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    categories = sa.table("categories", sa.column("name", sa.String()))
    op.bulk_insert(categories, [{"name": name} for name in DEFAULT_TAXONOMY])


def downgrade() -> None:
    op.execute("DELETE FROM categories WHERE org_id IS NULL")
    op.drop_column("line_items", "needs_category_review")
    op.drop_column("receipts", "categorization_error")
    op.drop_column("receipts", "categorization_status")
