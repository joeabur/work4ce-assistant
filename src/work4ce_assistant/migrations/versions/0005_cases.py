"""Tenant-scoped analyst assignment and escalation metadata.

Revision ID: 0005_cases
Revises: 0004_reviews
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_cases'
down_revision = '0004_reviews'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('case_coordination',
        sa.Column('investigation_id',sa.Text(),sa.ForeignKey('investigations.id'),primary_key=True),
        sa.Column('tenant',sa.Text(),primary_key=True),
        sa.Column('assignee',sa.Text()),
        sa.Column('escalation_state',sa.Text(),nullable=False),
        sa.Column('escalation_reason',sa.Text()),sa.Column('escalated_by',sa.Text()),sa.Column('escalated_at',sa.Text()),
        sa.Column('acknowledged_by',sa.Text()),sa.Column('acknowledged_at',sa.Text()),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('updated_by',sa.Text(),nullable=False),sa.Column('updated_at',sa.Text(),nullable=False),
        sa.CheckConstraint("escalation_state IN ('none','requested','acknowledged')",name='ck_case_escalation_state'),
        sa.CheckConstraint('revision >= 1 AND revision <= 2147483647',name='ck_case_revision'),
        sa.CheckConstraint('escalation_reason IS NULL OR length(escalation_reason) <= 1000',name='ck_case_reason_length'))
    op.create_index('ix_case_owner_queue','case_coordination',['tenant','assignee','updated_at'])


def downgrade() -> None:
    op.drop_index('ix_case_owner_queue',table_name='case_coordination')
    op.drop_table('case_coordination')
