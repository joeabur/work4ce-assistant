"""Single-source incident lifecycle and append-only analyst activity.

Revision ID: 0006_incidents
Revises: 0005_cases
"""
from alembic import op
import sqlalchemy as sa

revision = '0006_incidents'
down_revision = '0005_cases'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('incidents',
        sa.Column('id',sa.Text(),primary_key=True),
        sa.Column('investigation_id',sa.Text(),sa.ForeignKey('investigations.id'),nullable=False),
        sa.Column('tenant',sa.Text(),nullable=False),sa.Column('report_hash',sa.Text(),nullable=False),
        sa.Column('title',sa.Text(),nullable=False),sa.Column('description',sa.Text(),nullable=False),
        sa.Column('severity',sa.Text(),nullable=False),sa.Column('status',sa.Text(),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('created_by',sa.Text(),nullable=False),
        sa.Column('created_at',sa.Text(),nullable=False),sa.Column('updated_by',sa.Text(),nullable=False),
        sa.Column('updated_at',sa.Text(),nullable=False),sa.Column('resolution_note',sa.Text()),
        sa.Column('resolved_by',sa.Text()),sa.Column('resolved_at',sa.Text()),
        sa.Column('closed_by',sa.Text()),sa.Column('closed_at',sa.Text()),
        sa.UniqueConstraint('tenant','investigation_id',name='uq_incident_source'),
        sa.CheckConstraint("severity IN ('low','medium','high','critical')",name='ck_incident_severity'),
        sa.CheckConstraint("status IN ('open','in_progress','resolved','closed')",name='ck_incident_status'),
        sa.CheckConstraint('revision >= 1 AND revision <= 200',name='ck_incident_revision'))
    op.create_index('ix_incident_tenant_updated','incidents',['tenant','updated_at','id'])
    op.create_table('incident_activity',
        sa.Column('id',sa.Text(),primary_key=True),sa.Column('tenant',sa.Text(),nullable=False),
        sa.Column('incident_id',sa.Text(),sa.ForeignKey('incidents.id'),nullable=False),
        sa.Column('sequence',sa.Integer(),nullable=False),sa.Column('kind',sa.Text(),nullable=False),
        sa.Column('actor',sa.Text(),nullable=False),sa.Column('body',sa.Text(),nullable=False),
        sa.Column('evidence_ids',sa.Text(),nullable=False),sa.Column('from_status',sa.Text()),
        sa.Column('to_status',sa.Text()),sa.Column('created_at',sa.Text(),nullable=False),
        sa.UniqueConstraint('tenant','incident_id','sequence',name='uq_incident_activity_sequence'),
        sa.CheckConstraint("kind IN ('created','note','status')",name='ck_incident_activity_kind'),
        sa.CheckConstraint('sequence >= 1 AND sequence <= 200',name='ck_incident_activity_sequence'))


def downgrade() -> None:
    op.drop_table('incident_activity')
    op.drop_index('ix_incident_tenant_updated',table_name='incidents')
    op.drop_table('incidents')
