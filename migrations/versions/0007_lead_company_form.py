"""employer_leads: short company form (positions optional, website)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("employer_leads") as b:
        b.alter_column("positions", existing_type=sa.String(200), nullable=True)
        b.add_column(sa.Column("website", sa.String(200)))


def downgrade() -> None:
    with op.batch_alter_table("employer_leads") as b:
        b.drop_column("website")
        b.alter_column("positions", existing_type=sa.String(200), nullable=False)
