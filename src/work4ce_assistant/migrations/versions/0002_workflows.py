"""Durable, tenant/subject-scoped bounded investigation checkpoints.

Revision ID: 0002_workflows
Revises: 0001_foundation
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_workflows'
down_revision = '0001_foundation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('workflow_owner_locks',
        sa.Column('tenant', sa.Text(), primary_key=True),
        sa.Column('subject', sa.Text(), primary_key=True))
    op.create_table('workflow_state',
        sa.Column('id', sa.Text(), sa.ForeignKey('investigations.id'), primary_key=True),
        sa.Column('tenant', sa.Text(), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('idempotency_key', sa.Text(), nullable=False),
        sa.Column('request_hash', sa.Text(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('limit', sa.Integer(), nullable=False),
        sa.Column('max_tool_calls', sa.Integer(), nullable=False),
        sa.Column('tool_calls', sa.Integer(), nullable=False),
        sa.Column('deadline', sa.Float(), nullable=False),
        sa.Column('checkpoint', sa.Text()),
        sa.Column('checkpoint_hash', sa.Text()),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('lease_owner', sa.Text()),
        sa.Column('lease_until', sa.Float()),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.UniqueConstraint('tenant', 'subject', 'idempotency_key', name='uq_workflow_idempotency'),
        sa.CheckConstraint("state IN ('queued','running','collected','completed','failed','cancelled')", name='ck_workflow_state'),
        sa.CheckConstraint('tool_calls >= 0 AND tool_calls <= max_tool_calls AND max_tool_calls >= 1', name='ck_workflow_budget'),
        sa.CheckConstraint('revision >= 0', name='ck_workflow_revision'))


def downgrade() -> None:
    op.drop_table('workflow_state')
    op.drop_table('workflow_owner_locks')
