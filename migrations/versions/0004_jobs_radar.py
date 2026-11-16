"""jobs source radar tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_chats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tg_chat_id", sa.BigInteger, nullable=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("invite_hash", sa.String(64), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("members", sa.Integer, nullable=True),
        sa.Column("posts_per_day_7d", sa.Float, nullable=False, server_default="0"),
        sa.Column("ads_allowed", sa.String(8), nullable=False, server_default="unknown"),
        sa.Column("admin_contact", sa.String(120), nullable=True),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("land", sa.String(8), nullable=True),
        sa.Column("discovered_from", sa.String(8), nullable=False),
        sa.Column("discovered_via_chat_id", sa.Integer, nullable=True),
        sa.Column("entity_type", sa.String(8), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(16), nullable=False, server_default="candidate"),
        sa.Column("join_error", sa.String(120), nullable=True),
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("last_message_id", sa.BigInteger, nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tg_chat_id", name="uq_job_chats_tg_chat_id"),
        sa.UniqueConstraint("username", name="uq_job_chats_username"),
        sa.UniqueConstraint("invite_hash", name="uq_job_chats_invite_hash"),
    )
    op.create_index("ix_job_chats_status", "job_chats", ["status"])
    op.create_index("ix_job_chats_score", "job_chats", ["score"])

    op.create_table(
        "job_chat_daily",
        sa.Column("chat_id", sa.Integer, primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("posts", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "job_radar_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("chat_id", sa.Integer, nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.String(64), nullable=False),
    )
    op.create_index("ix_job_radar_actions_kind", "job_radar_actions", ["kind"])
    op.create_index("ix_job_radar_actions_at", "job_radar_actions", ["at"])

    op.create_table(
        "job_keywords",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("term", sa.String(80), nullable=False),
        sa.Column("lang", sa.String(4), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("term", "lang", "kind", name="uq_job_keywords_term_lang_kind"),
    )

    op.create_table(
        "job_signals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chat_id", sa.Integer, nullable=False),
        sa.Column("message_link", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("profession", sa.String(120), nullable=True),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_signals_chat_id", "job_signals", ["chat_id"])
    op.create_index("ix_job_signals_created_at", "job_signals", ["created_at"])

    op.create_table(
        "job_agencies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_norm", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(120), nullable=True),
        sa.Column("phone_norm", sa.String(32), nullable=True),
        sa.Column("email", sa.String(160), nullable=True),
        sa.Column("website", sa.String(200), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signals_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("digest_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_job_agencies_name_norm", "job_agencies", ["name_norm"])
    op.create_index("ix_job_agencies_domain", "job_agencies", ["domain"])
    op.create_index("ix_job_agencies_phone_norm", "job_agencies", ["phone_norm"])


def downgrade() -> None:
    for table in ("job_agencies", "job_signals", "job_keywords", "job_radar_actions", "job_chat_daily", "job_chats"):
        op.drop_table(table)
