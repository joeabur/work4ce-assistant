"""Bound multi-source incidents enforce intersected grants and qualified evidence."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from sqlalchemy import create_engine,select,text,update

import test_storage
from work4ce_assistant.contracts import Work4ceError,canonical,digest
from work4ce_assistant.incident_storage import FIELDS,IncidentRepository
from work4ce_assistant.storage import HEAD,Store,_config,incident_activity,incident_investigations,incidents_table,investigations,migrate

TENANT,OWNER='source-tenant','owner'
SOURCE_FIELDS={'investigation_id','primary','creator','assignee','escalation_state','query','linked_by','linked_at','evidence'}


class SourcesContract:
    @property
    def repository(self): return IncidentRepository(self.store)

    def source(self,*,owner=OWNER,tenant=TENANT,synthetic=True,count=1):
        identity=self.store.begin(tenant,owner)
        evidence=[{'evidence_id':'same' if index==0 else 'e-'+str(index),'content':{'summary':'Synthetic fact '+str(index)},
                   'private':'do not emit raw evidence'} for index in range(count)]
        self.store.finish(tenant,owner,identity,{'synthetic':synthetic,'query':'PowerShell','evidence':evidence,
            'private':'do not emit report metadata'},'completed')
        return identity

    def create(self,source=None,*,actor=OWNER,manage=False):
        return self.repository.create(TENANT,actor,source or self.source(),'Linked incident','Human context','high',manage=manage)

    def link(self,item,source,*,revision=None,actor=OWNER,manage=False):
        return self.repository.link_investigation(TENANT,actor,item['id'],revision or item['revision'],source,
                                                   'Correlated synthetic investigation',manage=manage)

    def test_source_link_primary_dto_and_lookup_from_either_investigation(self):
        primary=self.source()
        secondary=self.source(count=150)
        item=self.create(primary)
        linked=self.link(item,secondary)
        self.assertEqual(linked['revision'],2)
        self.assertEqual(set(linked),set(FIELDS))
        self.assertEqual(linked['investigation_id'],primary)
        self.assertEqual(self.repository.for_investigation(TENANT,OWNER,secondary),linked)
        sources=self.repository.sources(TENANT,OWNER,item['id'])
        self.assertEqual([row['investigation_id'] for row in sources],[primary,secondary])
        self.assertEqual([row['primary'] for row in sources],[True,False])
        self.assertTrue(all(set(row)==SOURCE_FIELDS for row in sources))
        self.assertEqual(sources[0]['escalation_state'],'none')
        self.assertEqual(len(sources[1]['evidence']),100)
        self.assertEqual(set(sources[0]['evidence'][0]),{'evidence_id','summary'})
        self.assertNotIn('do not emit',canonical(sources))
        activity=self.repository.activity(TENANT,OWNER,item['id'])
        self.assertEqual(activity[-1]['kind'],'linked')
        self.assertEqual(activity[-1]['linked_investigation_id'],secondary)
        self.assertEqual(activity[-1]['references'],[])
        self.assertEqual(activity[-1]['evidence_ids'],[])
        with self.assertRaisesRegex(Work4ceError,'incident_exists'):
            self.create(secondary)
        with self.assertRaisesRegex(Work4ceError,'incident_source_conflict'):
            self.link(linked,secondary)
        self.assertEqual(len(self.repository.list(TENANT,OWNER)),1)

    def test_all_source_acl_intersection_reassignment_and_filter_before_limit(self):
        visible=self.create()
        primary=self.source()
        private=self.source(owner='other-owner')
        hidden=self.create(primary,actor='manager',manage=True)
        hidden=self.link(hidden,private,actor='manager',manage=True)
        for access in (lambda:self.repository.get(TENANT,OWNER,hidden['id']),
                       lambda:self.repository.activity(TENANT,OWNER,hidden['id']),
                       lambda:self.repository.sources(TENANT,OWNER,hidden['id']),
                       lambda:self.repository.for_investigation(TENANT,OWNER,primary),
                       lambda:self.repository.add_note(TENANT,OWNER,hidden['id'],2,'Cannot access all sources')):
            with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
                access()
        self.assertEqual([row['id'] for row in self.repository.list(TENANT,OWNER,limit=1)],[visible['id']])
        self.assertEqual(len(self.repository.list(TENANT,'reviewer',all_cases=True)),2)
        # Owning just a secondary source must not reveal an existing group via create.
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.create(private,actor='other-owner')
        self.store.mutate_case(TENANT,'manager',private,0,'assign',assignee=OWNER,manage=True)
        self.assertEqual(self.repository.get(TENANT,OWNER,hidden['id'])['id'],hidden['id'])
        self.store.mutate_case(TENANT,'manager',private,1,'assign',assignee='another-analyst',manage=True)
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.get(TENANT,OWNER,hidden['id'])
        self.assertEqual([row['id'] for row in self.repository.list(TENANT,OWNER,limit=1)],[visible['id']])
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.get('foreign-tenant',OWNER,hidden['id'],all_cases=True)

    def test_unrelated_target_never_grants_group_access_or_exposes_conflict_identity(self):
        item=self.create()
        unrelated=self.source(owner='other-owner')
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.link(item,unrelated)
        self.assertEqual(len(self.repository.sources(TENANT,OWNER,item['id'])),1)
        target=self.create()
        with self.assertRaisesRegex(Work4ceError,'incident_source_conflict') as caught:
            self.link(item,target['investigation_id'])
        self.assertNotIn(target['id'],str(caught.exception))
        self.assertEqual(self.repository.get(TENANT,OWNER,item['id'])['revision'],1)

    def test_qualified_duplicate_ids_legacy_primary_and_validation(self):
        primary,secondary=self.source(),self.source()
        item=self.link(self.create(primary),secondary)
        refs=[{'investigation_id':primary,'evidence_id':'same'},{'investigation_id':secondary,'evidence_id':'same'}]
        self.repository.add_note(TENANT,OWNER,item['id'],2,'Two different source observations',references=refs)
        activity=self.repository.activity(TENANT,OWNER,item['id'])
        self.assertEqual(activity[-1]['references'],refs)
        self.assertEqual(activity[-1]['evidence_ids'],['same'])
        self.repository.add_note(TENANT,OWNER,item['id'],3,'Legacy primary reference',['same'])
        self.assertEqual(self.repository.activity(TENANT,OWNER,item['id'])[-1]['references'],refs[:1])
        unlinked=self.source()
        for invalid in ([refs[0],refs[0]],[{'investigation_id':unlinked,'evidence_id':'same'}],
                        [{'investigation_id':secondary,'evidence_id':'forged'}],
                        [{**refs[0],'tenant':'forged'}],[{'investigation_id':secondary,'evidence_id':True}],
                        refs*6,None,'not-a-list'):
            with self.assertRaisesRegex(Work4ceError,'invalid_incident_evidence'):
                self.repository.add_note(TENANT,OWNER,item['id'],4,'Invalid references',references=invalid)
        with self.assertRaisesRegex(Work4ceError,'invalid_incident_evidence'):
            self.repository.add_note(TENANT,OWNER,item['id'],4,'Mixed inputs',['same'],references=refs)
        self.assertEqual(self.repository.get(TENANT,OWNER,item['id'])['revision'],4)

    def test_source_count_active_status_and_all_source_escalation_barriers(self):
        item=self.create()
        for _ in range(9):
            item=self.link(item,self.source())
        self.assertEqual(len(self.repository.sources(TENANT,OWNER,item['id'])),10)
        with self.assertRaisesRegex(Work4ceError,'incident_source_limit'):
            self.link(item,self.source())
        other=self.create()
        secondary=self.source()
        other=self.link(other,secondary)
        self.store.mutate_case(TENANT,OWNER,secondary,0,'escalate',reason='Secondary source needs manager')
        self.assertEqual(self.repository.sources(TENANT,OWNER,other['id'])[1]['escalation_state'],'requested')
        with self.assertRaisesRegex(Work4ceError,'incident_escalation_pending'):
            self.repository.transition(TENANT,OWNER,other['id'],2,'resolved','Cannot bypass secondary escalation')
        self.store.mutate_case(TENANT,'manager',secondary,1,'acknowledge',manage=True)
        resolved=self.repository.transition(TENANT,OWNER,other['id'],2,'resolved','Disposition')
        with self.assertRaisesRegex(Work4ceError,'incident_not_active'):
            self.link(resolved,self.source())
        closed=self.repository.transition(TENANT,'manager',other['id'],3,'closed','Closure',manage=True)
        with self.assertRaisesRegex(Work4ceError,'incident_not_active'):
            self.link(closed,self.source())

    def test_all_source_hashes_checked_before_private_payload_and_original_records_unchanged(self):
        primary,secondary=self.source(),self.source()
        original={identity:self.store.get(TENANT,identity) for identity in (primary,secondary)}
        item=self.link(self.create(primary),secondary)
        self.repository.add_note(TENANT,OWNER,item['id'],2,'Human note',references=[{'investigation_id':secondary,'evidence_id':'same'}])
        for identity in (primary,secondary):
            self.assertEqual(self.store.get(TENANT,identity),original[identity])
            self.assertEqual(self.store.get_case(TENANT,OWNER,identity)['revision'],0)
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id==secondary).values(report='{}'))
        for access in (lambda:self.repository.get(TENANT,OWNER,item['id']),
                       lambda:self.repository.sources(TENANT,OWNER,item['id']),
                       lambda:self.repository.list(TENANT,OWNER),
                       lambda:self.repository.add_note(TENANT,OWNER,item['id'],3,'Must fail')):
            with self.assertRaisesRegex(Work4ceError,'incident_report_mismatch'):
                access()
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.get(TENANT,'outsider',item['id'])
        # Duplicate create remains an existence conflict independent of report state,
        # but only after the complete existing group visibility check.
        with self.assertRaisesRegex(Work4ceError,'incident_exists'):
            self.create(secondary)

    def test_history_rejects_reference_before_link_and_membership_mismatch(self):
        primary,secondary=self.source(),self.source()
        item=self.create(primary)
        self.repository.add_note(TENANT,OWNER,item['id'],1,'Before link',['same'])
        self.link(item,secondary,revision=2)
        with self.store.engine.begin() as connection:
            connection.execute(update(incident_activity).where(incident_activity.c.incident_id==item['id'],incident_activity.c.sequence==2).values(
                evidence_ids='[]',references=canonical([{'investigation_id':secondary,'evidence_id':'same'}])))
        with self.assertRaisesRegex(Work4ceError,'incident_integrity_failure'):
            self.repository.activity(TENANT,OWNER,item['id'])
        other=self.link(self.create(),self.source())
        with self.store.engine.begin() as connection:
            connection.execute(update(incident_activity).where(incident_activity.c.incident_id==other['id'],incident_activity.c.kind=='linked').values(linked_investigation_id=None))
        with self.assertRaisesRegex(Work4ceError,'incident_integrity_failure'):
            self.repository.sources(TENANT,OWNER,other['id'])
        missing=self.create()
        with self.store.engine.begin() as connection:
            connection.execute(incident_investigations.delete().where(incident_investigations.c.incident_id==missing['id']))
        with self.assertRaisesRegex(Work4ceError,'incident_integrity_failure'):
            self.repository.get(TENANT,OWNER,missing['id'])
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.get(TENANT,'outsider',missing['id'])

    def test_link_audit_rollback_and_revision_history_cap(self):
        item=self.create()
        secondary=self.source()
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.link(item,secondary)
        self.assertEqual(self.repository.get(TENANT,OWNER,item['id'])['revision'],1)
        self.assertEqual(len(self.repository.sources(TENANT,OWNER,item['id'])),1)
        self.assertEqual(len(self.repository.activity(TENANT,OWNER,item['id'])),1)
        self.assertEqual(self.create(secondary)['investigation_id'],secondary)
        for revision in range(1,200):
            self.repository.add_note(TENANT,OWNER,item['id'],revision,'Bounded activity')
        with self.assertRaisesRegex(Work4ceError,'incident_history_limit'):
            self.link(item,self.source(),revision=200)
        self.assertEqual(len(self.repository.activity(TENANT,OWNER,item['id'])),200)

    def test_snapshot_sources_survive_concurrent_link_commit(self):
        item=self.create()
        secondary=self.source()
        writer=Store(self.database)
        repository=self.repository
        original=repository._history
        def commit_between_context_and_history(connection,record,contexts):
            IncidentRepository(writer).link_investigation(TENANT,OWNER,item['id'],1,secondary,'Concurrent link')
            return original(connection,record,contexts)
        try:
            with patch.object(repository,'_history',side_effect=commit_between_context_and_history):
                snapshot=repository.sources(TENANT,OWNER,item['id'])
            self.assertEqual(len(snapshot),1)
            self.assertEqual(len(self.repository.sources(TENANT,OWNER,item['id'])),2)
        finally:
            writer.close()

    def test_membership_drift_aborts_without_extending_lock_order(self):
        item=self.create()
        secondary,target=self.source(),self.source()
        writer=Store(self.database)
        repository=self.repository
        original=repository._lock_parents
        called=False
        def commit_before_lock(connection,tenant,identities):
            nonlocal called
            if not called:
                called=True
                IncidentRepository(writer).link_investigation(TENANT,OWNER,item['id'],1,secondary,'Membership changed')
            return original(connection,tenant,identities)
        try:
            with patch.object(repository,'_lock_parents',side_effect=commit_before_lock),self.assertRaisesRegex(Work4ceError,'incident_revision_conflict'):
                repository.link_investigation(TENANT,OWNER,item['id'],1,target,'Stale discovered set')
            self.assertEqual({row['investigation_id'] for row in self.repository.sources(TENANT,OWNER,item['id'])},{item['investigation_id'],secondary})
            self.assertEqual(self.repository.get(TENANT,OWNER,item['id'])['revision'],2)
        finally:
            writer.close()

    def test_concurrent_link_and_create_have_one_binding_no_orphans(self):
        item=self.create()
        target=self.source()
        clients=[Store(self.database),Store(self.database)]
        barrier=threading.Barrier(2)
        def link():
            barrier.wait(timeout=5)
            try:
                IncidentRepository(clients[0]).link_investigation(TENANT,OWNER,item['id'],1,target,'Racing link')
                return 'linked'
            except Work4ceError as error:
                return error.code
        def create():
            barrier.wait(timeout=5)
            try:
                IncidentRepository(clients[1]).create(TENANT,OWNER,target,'Racing create','','low')
                return 'created'
            except Work4ceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes=[f.result(timeout=15) for f in (executor.submit(link),executor.submit(create))]
            self.assertIn(outcomes,(['linked','incident_exists'],['incident_source_conflict','created']))
            with self.store.engine.connect() as connection:
                bound=connection.execute(select(incident_investigations).where(incident_investigations.c.tenant==TENANT,
                    incident_investigations.c.investigation_id==target)).all()
                self.assertEqual(len(bound),1)
                all_incidents=connection.execute(select(incidents_table)).all()
                all_sources=connection.execute(select(incident_investigations)).all()
                self.assertTrue(all(any(m.incident_id==i.id and m.investigation_id==i.investigation_id for m in all_sources) for i in all_incidents))
        finally:
            for client in clients: client.close()

    def test_cross_link_sorted_parent_sets_do_not_deadlock(self):
        first,second=self.create(),self.create()
        clients=[Store(self.database),Store(self.database)]
        barrier=threading.Barrier(2)
        def link(client,item,target):
            barrier.wait(timeout=5)
            try:
                IncidentRepository(client).link_investigation(TENANT,OWNER,item['id'],1,target,'Cross-link attempt')
                return 'unexpected'
            except Work4ceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes=[f.result(timeout=15) for f in (executor.submit(link,clients[0],first,second['investigation_id']),
                    executor.submit(link,clients[1],second,first['investigation_id']))]
            self.assertEqual(outcomes,['incident_source_conflict','incident_source_conflict'])
            self.assertEqual(len(self.repository.list(TENANT,OWNER)),2)
        finally:
            for client in clients: client.close()


class SQLiteIncidentSourcesTests(SourcesContract,unittest.TestCase):
    def setUp(self): test_storage.SQLiteStoreTests.setUp(self)
    def tearDown(self): test_storage.SQLiteStoreTests.tearDown(self)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'),'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL incident sources unrun')
class PostgreSQLIncidentSourcesTests(SourcesContract,unittest.TestCase):
    def setUp(self): test_storage.PostgreSQLStoreTests.setUp(self)
    def tearDown(self): test_storage.PostgreSQLStoreTests.tearDown(self)


class IncidentSourcesMigrationTests(unittest.TestCase):
    def test_v6_primary_and_legacy_note_backfill_without_report_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            database=str(Path(directory)/'v6.db')
            engine=create_engine('sqlite:///'+database)
            identity=str(uuid4())
            primary='legacy-primary'
            created='2026-01-01T00:00:00+00:00'
            updated='2026-01-01T00:01:00+00:00'
            report={'synthetic':True,'query':'PowerShell','evidence':[{'evidence_id':'same','content':{'summary':'Retained source'}}]}
            with engine.begin() as connection:
                command.upgrade(_config(connection),'0006_incidents')
                connection.execute(investigations.insert().values(id=primary,tenant=TENANT,subject=OWNER,status='completed',
                    report=canonical(report),report_hash=digest(report),created_at=created,updated_at=created))
                connection.execute(incidents_table.insert().values(id=identity,tenant=TENANT,investigation_id=primary,report_hash=digest(report),
                    title='Migrated incident',description='Human context',severity='high',status='open',revision=2,
                    created_by=OWNER,created_at=created,updated_by=OWNER,updated_at=updated))
                connection.execute(incident_activity.insert().values(id=str(uuid4()),tenant=TENANT,incident_id=identity,sequence=1,
                    kind='created',actor=OWNER,body='Human context',evidence_ids='[]',from_status=None,to_status='open',created_at=created))
                connection.execute(incident_activity.insert().values(id=str(uuid4()),tenant=TENANT,incident_id=identity,sequence=2,
                    kind='note',actor=OWNER,body='Legacy note',evidence_ids='["same"]',created_at=updated))
            engine.dispose()
            migrate(database)
            migrate(database)
            store=Store(database)
            self.addCleanup(store.close)
            repository=IncidentRepository(store)
            self.assertEqual(repository.get(TENANT,OWNER,identity)['revision'],2)
            self.assertEqual(repository.sources(TENANT,OWNER,identity)[0]['investigation_id'],primary)
            note=repository.activity(TENANT,OWNER,identity)[1]
            self.assertEqual(note['evidence_ids'],['same'])
            self.assertEqual(note['references'],[{'investigation_id':primary,'evidence_id':'same'}])
            self.assertIsNone(note['linked_investigation_id'])
            self.assertEqual(store.get(TENANT,primary)['report'],report)
            with store.engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),HEAD)
