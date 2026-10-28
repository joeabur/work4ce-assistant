"""Initial tenant-scoped investigations, audit, and connector state.

Revision ID: 0001_foundation
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("investigations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tenant", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("report", sa.Text()), sa.Column("report_hash", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False))
    op.create_table("audit",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False), sqlite_autoincrement=True)
    op.create_table("connector_state",
        sa.Column("tenant", sa.Text(), primary_key=True),
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("enabled", sa.Integer(), nullable=False))


def downgrade() -> None:
    op.drop_table("connector_state")
    op.drop_table("audit")
    op.drop_table("investigations")
