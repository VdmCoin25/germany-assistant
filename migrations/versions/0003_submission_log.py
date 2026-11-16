"""submission log for per-user form limits

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submission_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_tg", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_submission_log_owner_tg", "submission_log", ["owner_tg"])
    op.create_index("ix_submission_log_created_at", "submission_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("submission_log")
