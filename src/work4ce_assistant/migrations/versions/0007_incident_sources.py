"""Bound incident source membership and qualified evidence references.

Revision ID: 0007_incident_sources
Revises: 0006_incidents
"""
from alembic import op
import sqlalchemy as sa

revision='0007_incident_sources'
down_revision='0006_incidents'
branch_labels=None
depends_on=None


def upgrade() -> None:
    op.create_table('incident_investigations',
        sa.Column('tenant',sa.Text(),primary_key=True),
        sa.Column('investigation_id',sa.Text(),sa.ForeignKey('investigations.id'),primary_key=True),
        sa.Column('incident_id',sa.Text(),sa.ForeignKey('incidents.id'),nullable=False),
        sa.Column('report_hash',sa.Text(),nullable=False),sa.Column('linked_by',sa.Text(),nullable=False),
        sa.Column('linked_at',sa.Text(),nullable=False))
    op.create_index('ix_incident_sources','incident_investigations',['tenant','incident_id'])
    op.execute(sa.text('''INSERT INTO incident_investigations(tenant,investigation_id,incident_id,report_hash,linked_by,linked_at)
        SELECT tenant,investigation_id,id,report_hash,created_by,created_at FROM incidents'''))
    with op.batch_alter_table('incident_activity') as batch:
        batch.add_column(sa.Column('references',sa.Text(),nullable=False,server_default='[]'))
        batch.add_column(sa.Column('linked_investigation_id',sa.Text(),nullable=True))
        batch.drop_constraint('ck_incident_activity_kind',type_='check')
        batch.create_check_constraint('ck_incident_activity_kind',"kind IN ('created','note','status','linked')")


def downgrade() -> None:
    # Linked histories have no lossless v6 representation.
    if op.get_bind().execute(sa.text("SELECT count(*) FROM incident_activity WHERE kind='linked'")).scalar():
        raise RuntimeError('Cannot downgrade incidents with linked source history')
    with op.batch_alter_table('incident_activity') as batch:
        batch.drop_constraint('ck_incident_activity_kind',type_='check')
        batch.create_check_constraint('ck_incident_activity_kind',"kind IN ('created','note','status')")
        batch.drop_column('linked_investigation_id')
        batch.drop_column('references')
    op.drop_index('ix_incident_sources',table_name='incident_investigations')
    op.drop_table('incident_investigations')
