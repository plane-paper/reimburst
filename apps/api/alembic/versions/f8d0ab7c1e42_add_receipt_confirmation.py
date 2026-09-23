"""Persist reviewed receipt confirmations.

Revision ID: f8d0ab7c1e42
Revises: a7f25c8163d1
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8d0ab7c1e42"
down_revision: Union[str, Sequence[str], None] = "a7f25c8163d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("receipts", "confirmed_at")
