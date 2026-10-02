"""freeze CSV payout rows and allow only one payout per request.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payouts", sa.Column("employee_email", sa.String(length=320), nullable=True))
    op.add_column("payouts", sa.Column("amount_cents", sa.Integer(), nullable=True))
    op.add_column("payouts", sa.Column("currency", sa.String(length=3), nullable=True))
    op.execute(
        "UPDATE payouts SET employee_email = '', amount_cents = 0, currency = '' "
        "WHERE employee_email IS NULL"
    )
    op.alter_column("payouts", "employee_email", nullable=False)
    op.alter_column("payouts", "amount_cents", nullable=False)
    op.alter_column("payouts", "currency", nullable=False)
    op.create_unique_constraint("uq_payouts_request_id", "payouts", ["request_id"])


def downgrade() -> None:
    op.drop_constraint("uq_payouts_request_id", "payouts", type_="unique")
    op.drop_column("payouts", "currency")
    op.drop_column("payouts", "amount_cents")
    op.drop_column("payouts", "employee_email")
