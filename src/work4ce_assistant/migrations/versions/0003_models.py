"""Durable model reservations, immutable workflow routing, and validated cache.

Revision ID: 0003_models
Revises: 0002_workflows
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_models'
down_revision = '0002_workflows'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, datatype in [('reasoning_config_hash', sa.Text()), ('model_limits_hash', sa.Text()),
                           ('max_model_calls', sa.Integer()), ('max_model_tokens', sa.Integer()),
                           ('max_model_cost_microusd', sa.Integer())]:
        op.add_column('workflow_state', sa.Column(name, datatype, nullable=True))
    op.create_table('model_attempts',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('workflow_id', sa.Text(), sa.ForeignKey('workflow_state.id'), nullable=False),
        sa.Column('tenant', sa.Text(), nullable=False), sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('stage', sa.Text(), nullable=False), sa.Column('input_hash', sa.Text(), nullable=False),
        sa.Column('config_hash', sa.Text(), nullable=False), sa.Column('state', sa.Text(), nullable=False),
        sa.Column('result', sa.Text()), sa.Column('result_hash', sa.Text()),
        sa.Column('reserved_tokens', sa.Integer(), nullable=False),
        sa.Column('reserved_cost_microusd', sa.Integer(), nullable=False),
        sa.Column('actual_input_tokens', sa.Integer()), sa.Column('actual_output_tokens', sa.Integer()),
        sa.Column('actual_cost_microusd', sa.Integer()), sa.Column('error_code', sa.Text()),
        sa.Column('completion_revision', sa.Integer()),
        sa.CheckConstraint("stage IN ('plan','assessment')", name='ck_model_stage'),
        sa.CheckConstraint("state IN ('reserved','completed','failed')", name='ck_model_state'),
        sa.CheckConstraint('reserved_tokens > 0 AND reserved_cost_microusd >= 0', name='ck_model_reservation'),
        sa.CheckConstraint('actual_input_tokens IS NULL OR actual_input_tokens >= 0', name='ck_model_input_usage'),
        sa.CheckConstraint('actual_output_tokens IS NULL OR actual_output_tokens >= 0', name='ck_model_output_usage'),
        sa.CheckConstraint('actual_cost_microusd IS NULL OR actual_cost_microusd >= 0', name='ck_model_cost_usage'))
    op.create_index('ix_model_cache', 'model_attempts',
                    ['workflow_id', 'stage', 'input_hash', 'config_hash', 'state'])


def downgrade() -> None:
    op.drop_index('ix_model_cache', table_name='model_attempts')
    op.drop_table('model_attempts')
    for name in ['max_model_cost_microusd', 'max_model_tokens', 'max_model_calls', 'model_limits_hash', 'reasoning_config_hash']:
        op.drop_column('workflow_state', name)
