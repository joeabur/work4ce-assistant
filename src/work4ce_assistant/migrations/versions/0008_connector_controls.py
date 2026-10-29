"""Versioned connector administration and bound review metadata.

Revision ID: 0008_connector_controls
Revises: 0007_incident_sources
"""
from alembic import op
import sqlalchemy as sa

revision='0008_connector_controls'
down_revision='0007_incident_sources'
branch_labels=None
depends_on=None


def upgrade() -> None:
    with op.batch_alter_table('connector_state') as batch:
        batch.add_column(sa.Column('revision',sa.Integer(),nullable=False,server_default='0'))
        for name in ('changed_by','changed_at','change_reason','review_manifest_hash','reviewed_by','reviewed_at','review_reason'):
            batch.add_column(sa.Column(name,sa.Text(),nullable=True))


def downgrade() -> None:
    # Older schemas cannot retain review/revision history. Do not silently erase it.
    if op.get_bind().execute(sa.text('SELECT count(*) FROM connector_state WHERE revision<>0')).scalar():
        raise RuntimeError('Cannot downgrade connector administration history')
    with op.batch_alter_table('connector_state') as batch:
        for name in ('review_reason','reviewed_at','reviewed_by','review_manifest_hash','change_reason','changed_at','changed_by','revision'):
            batch.drop_column(name)
