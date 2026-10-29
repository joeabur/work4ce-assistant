"""Durable connector review/enable CAS boundaries on SQLite and PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from sqlalchemy import create_engine,inspect,select,text,update

import test_storage
from work4ce_assistant.contracts import Work4ceError,canonical,digest
from work4ce_assistant.storage import (HEAD,Store,_config,connector_state,investigations,report_reviews,
    response_approvals,case_coordination,incidents_table,incident_activity,incident_investigations,migrate)

TENANT,IDENTITY='connector-tenant','demo-rest'
MANIFEST='a'*64


class ConnectorControlsContract:
    def initialize(self):
        self.store.initialize_connector(TENANT,IDENTITY)

    def state(self):
        return self.store.connector_administration(TENANT,IDENTITY)

    def change(self,revision,enabled,reason='Operator decision.',**kwargs):
        return self.store.change_connector_state(TENANT,'admin',IDENTITY,revision,enabled,reason,**kwargs)

    def test_initialization_is_idempotent_and_state_reads_are_scoped(self):
        self.initialize()
        before=self.store.audit_rows(TENANT)
        self.assertEqual(self.state(),{'enabled':True,'revision':0,'last_change':None,'last_review':None})
        self.initialize()
        self.assertEqual(self.state()['revision'],0)
        self.assertEqual(self.store.audit_rows(TENANT),before)
        for tenant,identity in (('other-tenant',IDENTITY),(TENANT,'missing-source')):
            with self.assertRaisesRegex(Work4ceError,'connector_not_found'):
                self.store.connector_administration(tenant,identity)

    def test_review_enable_binds_hash_actor_reason_and_keeps_review_on_disable(self):
        self.initialize()
        disabled=self.change(0,False,' Pause source. ')
        self.assertFalse(disabled['enabled'])
        self.assertEqual(disabled['last_change']['reason'],'Pause source.')
        enabled=self.change(1,True,' Revalidated the registered definition. ',manifest_hash=MANIFEST)
        self.assertTrue(enabled['enabled'])
        self.assertEqual(enabled['revision'],2)
        self.assertEqual(enabled['last_review'],{'manifest_hash':MANIFEST,**enabled['last_change']})
        self.assertEqual(enabled['last_review']['actor'],'admin')
        self.assertEqual(enabled['last_review']['reason'],'Revalidated the registered definition.')
        disabled=self.change(2,False)
        self.assertEqual(disabled['last_review'],enabled['last_review'])
        self.assertEqual(self.store.audit_rows(TENANT),[
            ('connector.disable',IDENTITY,'revision:1'),('connector.review_enable',IDENTITY,'revision:2'),
            ('connector.disable',IDENTITY,'revision:3')])
        self.assertNotIn('Operator decision.',str(self.store.audit_rows(TENANT)))

    def test_legacy_disable_always_fences_revision_and_bootstrap_never_reenables(self):
        self.initialize()
        self.store.disable(TENANT,'legacy-admin',IDENTITY)
        first=self.state()
        self.assertEqual(first['revision'],1)
        self.store.disable(TENANT,'legacy-admin',IDENTITY)
        self.assertEqual(self.state()['revision'],2)
        self.initialize()
        self.assertFalse(self.state()['enabled'])
        self.assertEqual(self.state()['revision'],2)
        with self.assertRaisesRegex(Work4ceError,'connector_revision_conflict'):
            self.change(1,True,manifest_hash=MANIFEST)
        enabled=self.change(2,True,manifest_hash=MANIFEST)
        self.store.disable(TENANT,'legacy-admin',IDENTITY)
        self.assertEqual(self.state()['last_review'],enabled['last_review'])
        self.assertEqual(self.state()['last_change']['actor'],'legacy-admin')
        self.assertEqual(self.store.audit_rows(TENANT)[:2],[('connector.disable',IDENTITY,'disabled')]*2)
        self.assertEqual(self.store.audit_rows(TENANT)[-1],('connector.disable',IDENTITY,'disabled'))

    def test_stale_same_state_and_foreign_updates_have_no_effect(self):
        self.initialize()
        self.change(0,False)
        before=self.state()
        audit=self.store.audit_rows(TENANT)
        for revision,enabled,kwargs in ((0,True,{'manifest_hash':MANIFEST}),(1,False,{})):
            with self.assertRaisesRegex(Work4ceError,'connector_revision_conflict'):
                self.change(revision,enabled,**kwargs)
        with self.assertRaisesRegex(Work4ceError,'connector_not_found'):
            self.store.change_connector_state('other-tenant','admin',IDENTITY,1,True,'Other tenant.',manifest_hash=MANIFEST)
        self.assertEqual(self.state(),before)
        self.assertEqual(self.store.audit_rows(TENANT),audit)

    def test_validation_rejects_ambiguous_revisions_flags_reasons_hashes_and_scopes(self):
        self.initialize()
        for revision in (-1,2147483647,True,'0'):
            with self.assertRaisesRegex(Work4ceError,'invalid_connector_update'):
                self.change(revision,False)
        for enabled in (0,1,'false',None):
            with self.assertRaisesRegex(Work4ceError,'invalid_connector_update'):
                self.change(0,enabled)
        for reason in ('','  ','x'*1001,None,True):
            with self.assertRaisesRegex(Work4ceError,'invalid_connector_update'):
                self.change(0,False,reason)
        for manifest in (None,'','A'*64,'a'*63,'g'*64,False):
            with self.assertRaisesRegex(Work4ceError,'invalid_connector_update'):
                self.change(0,True,manifest_hash=manifest)
        with self.assertRaisesRegex(Work4ceError,'invalid_connector_update'):
            self.change(0,False,manifest_hash=MANIFEST)
        for tenant,subject,identity in (('', 'admin',IDENTITY),(TENANT,' ',IDENTITY),(TENANT,None,IDENTITY),
                                       (TENANT,True,IDENTITY),(TENANT,'admin','bad/source')):
            with self.assertRaisesRegex(Work4ceError,'invalid_connector_update'):
                self.store.change_connector_state(tenant,subject,identity,0,False,'Reason.')
        self.assertEqual(self.state()['revision'],0)
        self.assertEqual(self.store.audit_rows(TENANT),[])

    def test_audit_failure_rolls_back_both_disablement_and_review_enable(self):
        self.initialize()
        before=self.state()
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled failure')):
            with self.assertRaises(RuntimeError):
                self.change(0,False)
        self.assertEqual(self.state(),before)
        self.change(0,False)
        before=self.state()
        audit=self.store.audit_rows(TENANT)
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled failure')):
            with self.assertRaises(RuntimeError):
                self.change(1,True,manifest_hash=MANIFEST)
        self.assertEqual(self.state(),before)
        self.assertEqual(self.store.audit_rows(TENANT),audit)
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled failure')):
            with self.assertRaises(RuntimeError):
                self.store.disable(TENANT,'legacy-admin',IDENTITY)
        self.assertEqual(self.state(),before)

    def test_review_and_disabled_state_survive_reopen_and_bootstrap(self):
        self.initialize()
        self.change(0,False)
        self.change(1,True,manifest_hash=MANIFEST)
        before=self.change(2,False)
        self.store.close()
        self.store=Store(self.database)
        self.initialize()
        self.assertEqual(self.state(),before)

    def test_two_store_disable_race_has_one_cas_winner_and_one_audit(self):
        self.initialize()
        clients=[Store(self.database),Store(self.database)]
        barrier=threading.Barrier(2)
        def change(client):
            barrier.wait(timeout=5)
            try:
                return client.change_connector_state(TENANT,'admin',IDENTITY,0,False,'Concurrent change.')['revision']
            except Work4ceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes=list(pool.map(change,clients))
            self.assertCountEqual(outcomes,[1,'connector_revision_conflict'])
            self.assertEqual(self.state()['revision'],1)
            self.assertEqual(self.store.audit_rows(TENANT),[('connector.disable',IDENTITY,'revision:1')])
        finally:
            for client in clients: client.close()

    def test_legacy_disable_wins_over_a_concurrent_prevalidated_enable(self):
        self.initialize()
        self.store.disable(TENANT,'admin',IDENTITY)
        clients=[Store(self.database),Store(self.database)]
        barrier=threading.Barrier(2)
        def enable():
            barrier.wait(timeout=5)
            try:
                return clients[0].change_connector_state(TENANT,'admin',IDENTITY,1,True,'Validated before race.',manifest_hash=MANIFEST)['revision']
            except Work4ceError as error:
                return error.code
        def disable():
            barrier.wait(timeout=5)
            clients[1].disable(TENANT,'emergency-admin',IDENTITY)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                future=pool.submit(enable)
                other=pool.submit(disable)
                self.assertIn(future.result(timeout=15),(2,'connector_revision_conflict'))
                other.result(timeout=15)
            self.assertFalse(self.state()['enabled'])
            self.assertIn(self.state()['revision'],(2,3))
            self.assertEqual(self.state()['last_change']['actor'],'emergency-admin')
            with self.assertRaisesRegex(Work4ceError,'connector_revision_conflict'):
                self.change(1,True,manifest_hash=MANIFEST)
        finally:
            for client in clients: client.close()

    def test_stored_metadata_is_validated_before_read_or_mutation(self):
        self.initialize()
        with self.store.engine.connect() as connection:
            original=dict(connection.execute(select(connector_state).where(connector_state.c.tenant==TENANT)).one()._mapping)
        stamp=datetime.now(timezone.utc).isoformat()
        corruptions=[{'enabled':2},{'revision':-1},{'changed_by':'admin'},
            {'revision':1}, {'revision':1,'changed_by':'admin','changed_at':stamp,'change_reason':'Reason.'},
            {'enabled':0,'revision':1,'changed_by':'admin','changed_at':'naive','change_reason':'Reason.'},
            {'enabled':0,'revision':1,'changed_by':'admin','changed_at':stamp,'change_reason':' trailing '},
            {'enabled':0,'revision':1,'changed_by':'admin','changed_at':stamp,'change_reason':'Reason.','review_manifest_hash':MANIFEST},
            {'enabled':0,'revision':1,'changed_by':'admin','changed_at':stamp,'change_reason':'Reason.',
             'reviewed_by':'reviewer','reviewed_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
             'review_reason':'Future review.','review_manifest_hash':MANIFEST}]
        for corrupted in corruptions:
            with self.store.engine.begin() as connection:
                connection.execute(update(connector_state).where(connector_state.c.tenant==TENANT).values(**{**original,**corrupted}))
            with self.assertRaisesRegex(Work4ceError,'connector_state_integrity_failure'):
                self.state()
            with self.assertRaisesRegex(Work4ceError,'connector_state_integrity_failure'):
                self.change(0,False)
            with self.store.engine.begin() as connection:
                connection.execute(update(connector_state).where(connector_state.c.tenant==TENANT).values(**original))


class SQLiteConnectorControlsTests(ConnectorControlsContract,unittest.TestCase):
    def setUp(self): test_storage.SQLiteStoreTests.setUp(self)
    def tearDown(self): test_storage.SQLiteStoreTests.tearDown(self)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'),'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL connector controls unrun')
class PostgreSQLConnectorControlsTests(ConnectorControlsContract,unittest.TestCase):
    def setUp(self): test_storage.PostgreSQLStoreTests.setUp(self)
    def tearDown(self): test_storage.PostgreSQLStoreTests.tearDown(self)


class ConnectorControlsMigrationTests(unittest.TestCase):
    def test_v7_rows_and_all_nonconnector_data_survive_without_implicit_enablement(self):
        with tempfile.TemporaryDirectory() as directory:
            database=str(Path(directory)/'v7.db')
            engine=create_engine('sqlite:///'+database)
            instant='2026-10-29T12:00:00+00:00'
            source,incident=str(uuid4()),str(uuid4())
            report={'synthetic':True,'evidence':[]}
            report_hash=digest(report)
            with engine.begin() as connection:
                command.upgrade(_config(connection),'0007_incident_sources')
                connection.execute(text("INSERT INTO connector_state(tenant,id,enabled) VALUES (:tenant,'demo-rest',0),(:tenant,'demo-mcp',1)"),{'tenant':TENANT})
                connection.execute(investigations.insert().values(id=source,tenant=TENANT,subject='owner',status='completed',
                    report=canonical(report),report_hash=report_hash,created_at=instant,updated_at=instant))
                connection.execute(report_reviews.insert().values(investigation_id=source,review_id='review',tenant=TENANT,
                    requester='owner',report_hash=report_hash,state='approved',expires_at=1,reviewer='reviewer',comment='Retained review.'))
                connection.execute(response_approvals.insert().values(id='approval',investigation_id=source,tenant=TENANT,requester='owner',
                    report_hash=report_hash,action='endpoint.isolate',target='demo-host-1',parameters='{}',request_hash='b'*64,state='pending',expires_at=1))
                connection.execute(case_coordination.insert().values(investigation_id=source,tenant=TENANT,assignee='admin',escalation_state='none',
                    revision=1,updated_by='owner',updated_at=instant))
                connection.execute(incidents_table.insert().values(id=incident,investigation_id=source,tenant=TENANT,report_hash=report_hash,
                    title='Preserved incident',description='Retained context.',severity='medium',status='open',revision=1,
                    created_by='owner',created_at=instant,updated_by='owner',updated_at=instant))
                connection.execute(incident_activity.insert().values(id=str(uuid4()),tenant=TENANT,incident_id=incident,sequence=1,kind='created',
                    actor='owner',body='Retained context.',evidence_ids='[]',created_at=instant,references='[]'))
                connection.execute(incident_investigations.insert().values(tenant=TENANT,investigation_id=source,incident_id=incident,
                    report_hash=report_hash,linked_by='owner',linked_at=instant))
                names=set(inspect(connection).get_table_names())-{'connector_state','alembic_version'}
                before={name:connection.exec_driver_sql('SELECT * FROM "'+name+'"').all() for name in names}
            engine.dispose()
            migrate(database)
            migrate(database)
            store=Store(database)
            try:
                self.assertEqual(store.connector_administration(TENANT,'demo-rest'),{
                    'enabled':False,'revision':0,'last_change':None,'last_review':None})
                self.assertTrue(store.connector_administration(TENANT,'demo-mcp')['enabled'])
                store.initialize_connector(TENANT,'demo-rest')
                self.assertFalse(store.enabled(TENANT,'demo-rest'))
                with store.engine.connect() as connection:
                    self.assertEqual({name:connection.exec_driver_sql('SELECT * FROM "'+name+'"').all() for name in names},before)
                    self.assertEqual(connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),HEAD)
            finally: store.close()
