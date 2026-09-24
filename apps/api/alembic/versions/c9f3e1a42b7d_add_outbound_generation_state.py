"""Track asynchronous outbound artifact generation.

Revision ID: c9f3e1a42b7d
Revises: f8d0ab7c1e42
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9f3e1a42b7d"
down_revision: Union[str, Sequence[str], None] = "f8d0ab7c1e42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    status = sa.Enum("PENDING", "PROCESSING", "SUCCEEDED", "FAILED", name="extraction_status")
    op.add_column("outbound_requests", sa.Column("generation_status", status, nullable=False, server_default="PENDING"))
    op.add_column("outbound_requests", sa.Column("generation_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("outbound_requests", "generation_error")
    op.drop_column("outbound_requests", "generation_status")
