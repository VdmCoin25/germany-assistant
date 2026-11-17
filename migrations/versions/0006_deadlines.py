"""deadlines: user dates with reminders

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deadlines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_tg", sa.BigInteger, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("due", sa.Date, nullable=False),
        sa.Column("sent_3", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sent_1", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_deadlines_owner_tg", "deadlines", ["owner_tg"])
    op.create_index("ix_deadlines_due", "deadlines", ["due"])


def downgrade() -> None:
    op.drop_table("deadlines")
