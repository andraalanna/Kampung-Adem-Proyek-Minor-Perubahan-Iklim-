"""rw_status.escalated: remember that a level was reached by escalation

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rw_status", sa.Column("escalated", sa.Boolean(), nullable=False,
                                         server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("rw_status", "escalated")
