"""job exchange: seekers, employers, vacancies, contact requests

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _ts(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "seeker_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_tg", sa.BigInteger, nullable=False),
        sa.Column("position", sa.String(120), nullable=False),
        sa.Column("land", sa.String(8)),
        sa.Column("city", sa.String(80)),
        sa.Column("german_level", sa.String(8)),
        sa.Column("employment", sa.String(16), nullable=False),
        sa.Column("shifts_ok", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("experience", sa.Text, nullable=False),
        sa.Column("about", sa.Text),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_seeker_profiles_owner_tg", "seeker_profiles", ["owner_tg"], unique=True)
    op.create_index("ix_seeker_profiles_status", "seeker_profiles", ["status"])

    op.create_table(
        "employers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_tg", sa.BigInteger, nullable=False),
        sa.Column("company", sa.String(160), nullable=False),
        sa.Column("address", sa.String(240), nullable=False),
        sa.Column("register_no", sa.String(80), nullable=False),
        sa.Column("contact_person", sa.String(120), nullable=False),
        sa.Column("contact", sa.String(160), nullable=False),
        sa.Column("website", sa.String(200)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        _ts("access_until", True), _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_employers_owner_tg", "employers", ["owner_tg"], unique=True)
    op.create_index("ix_employers_status", "employers", ["status"])

    op.create_table(
        "vacancies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employer_id", sa.Integer, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("land", sa.String(8)),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("german_level", sa.String(8)),
        sa.Column("employment", sa.String(16), nullable=False),
        sa.Column("salary", sa.String(80)),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        _ts("expires_at", True), _ts("created_at"),
    )
    op.create_index("ix_vacancies_employer_id", "vacancies", ["employer_id"])
    op.create_index("ix_vacancies_status", "vacancies", ["status"])

    op.create_table(
        "contact_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("employer_id", sa.Integer, nullable=False),
        sa.Column("seeker_id", sa.Integer, nullable=False),
        sa.Column("vacancy_id", sa.Integer),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        _ts("created_at"), _ts("answered_at", True),
    )
    op.create_index("ix_contact_requests_employer_id", "contact_requests", ["employer_id"])
    op.create_index("ix_contact_requests_seeker_id", "contact_requests", ["seeker_id"])
    op.create_index("ix_contact_requests_status", "contact_requests", ["status"])


def downgrade() -> None:
    for t in ("contact_requests", "vacancies", "employers", "seeker_profiles"):
        op.drop_table(t)
