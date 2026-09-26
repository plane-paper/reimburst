"""add organization request synopsis state

Revision ID: d7f6a8b9c0d1
Revises: c9f3e1a42b7d
Create Date: 2026-09-24 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7f6a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "c9f3e1a42b7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reimbursement_requests",
        sa.Column(
            "synopsis_status",
            sa.Enum("PENDING", "PROCESSING", "SUCCEEDED", "FAILED", name="extraction_status"),
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column("reimbursement_requests", sa.Column("synopsis_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reimbursement_requests", "synopsis_error")
    op.drop_column("reimbursement_requests", "synopsis_status")
