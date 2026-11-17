"""employer leads: short hiring requests reviewed by an admin

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employer_leads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_tg", sa.BigInteger, nullable=False),
        sa.Column("contact", sa.String(160), nullable=False),
        sa.Column("contact_person", sa.String(120)),
        sa.Column("company", sa.String(160)),
        sa.Column("positions", sa.String(200), nullable=False),
        sa.Column("headcount", sa.Integer),
        sa.Column("land", sa.String(8)),
        sa.Column("city", sa.String(80)),
        sa.Column("details", sa.Text),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_employer_leads_owner_tg", "employer_leads", ["owner_tg"])
    op.create_index("ix_employer_leads_status", "employer_leads", ["status"])


def downgrade() -> None:
    op.drop_table("employer_leads")
