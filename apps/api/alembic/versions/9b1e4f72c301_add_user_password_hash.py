"""add password hashes for local authentication.

Revision ID: 9b1e4f72c301
Revises: d7f6a8b9c0d1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9b1e4f72c301"
down_revision: Union[str, Sequence[str], None] = "d7f6a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
