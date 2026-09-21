"""Persist receipt extraction lifecycle and currency.

Revision ID: 41c1d4a2b0e9
Revises: e3a0fa94e287
Create Date: 2026-09-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "41c1d4a2b0e9"
down_revision: Union[str, Sequence[str], None] = "e3a0fa94e287"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    extraction_status = sa.Enum(
        "PENDING", "PROCESSING", "SUCCEEDED", "FAILED", name="extraction_status"
    )
    extraction_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "receipts",
        sa.Column(
            "extraction_status",
            extraction_status,
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column("receipts", sa.Column("extraction_error", sa.Text(), nullable=True))
    op.add_column("receipts", sa.Column("currency", sa.String(length=3), nullable=True))


def downgrade() -> None:
    op.drop_column("receipts", "currency")
    op.drop_column("receipts", "extraction_error")
    op.drop_column("receipts", "extraction_status")
    sa.Enum(name="extraction_status").drop(op.get_bind(), checkfirst=True)
