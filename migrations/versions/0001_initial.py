"""initial: users, analytics_events, info_sources

Revision ID: 0001
Revises:
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=False),
        sa.Column("language", sa.String(8)),
        sa.Column("land", sa.String(8)),
        sa.Column("city", sa.String(80)),
        sa.Column("german_level", sa.String(8)),
        sa.Column("goal", sa.String(16)),
        sa.Column("residence_status", sa.String(16)),
        sa.Column("is_registered", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_blocked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("broadcast_consent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("feature", sa.String(64)),
        sa.Column("user_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analytics_events_name", "analytics_events", ["name"])
    op.create_index("ix_analytics_events_user_hash", "analytics_events", ["user_hash"])
    op.create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])

    op.create_table(
        "info_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("topic", sa.String(32), nullable=False),
        sa.Column("title_uk", sa.String(200), nullable=False),
        sa.Column("title_ru", sa.String(200), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_info_sources_topic", "info_sources", ["topic"])


def downgrade() -> None:
    op.drop_table("info_sources")
    op.drop_table("analytics_events")
    op.drop_table("users")
