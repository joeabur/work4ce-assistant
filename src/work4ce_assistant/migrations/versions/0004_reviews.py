"""Human report review and single-use synthetic response approvals.

Revision ID: 0004_reviews
Revises: 0003_models
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_reviews'
down_revision = '0003_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('workflow_state', sa.Column('review_required', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('report_reviews',
        sa.Column('investigation_id', sa.Text(), sa.ForeignKey('investigations.id'), primary_key=True),
        sa.Column('review_id', sa.Text(), nullable=False, unique=True),
        sa.Column('tenant', sa.Text(), nullable=False), sa.Column('requester', sa.Text(), nullable=False),
        sa.Column('report_hash', sa.Text(), nullable=False), sa.Column('state', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False), sa.Column('reviewer', sa.Text()), sa.Column('comment', sa.Text()),
        sa.CheckConstraint("state IN ('pending','approved','rejected')", name='ck_report_review_state'))
    op.create_table('response_approvals',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('investigation_id', sa.Text(), sa.ForeignKey('investigations.id'), nullable=False),
        sa.Column('tenant', sa.Text(), nullable=False), sa.Column('requester', sa.Text(), nullable=False),
        sa.Column('report_hash', sa.Text(), nullable=False), sa.Column('action', sa.Text(), nullable=False),
        sa.Column('target', sa.Text(), nullable=False), sa.Column('parameters', sa.Text(), nullable=False),
        sa.Column('request_hash', sa.Text(), nullable=False), sa.Column('state', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False), sa.Column('approver', sa.Text()),
        sa.Column('approval_id', sa.Text(), unique=True), sa.Column('decision_comment', sa.Text()),
        sa.Column('simulation_result', sa.Text()), sa.Column('simulation_result_hash', sa.Text()),
        sa.CheckConstraint("state IN ('pending','approved','rejected','revoked','consumed')", name='ck_response_state'))
    op.create_index('ix_response_owner_pending', 'response_approvals', ['tenant','requester','state'])


def downgrade() -> None:
    op.drop_index('ix_response_owner_pending', table_name='response_approvals')
    op.drop_table('response_approvals')
    op.drop_table('report_reviews')
    op.drop_column('workflow_state', 'review_required')
