"""Incident coordination is scoped, bounded, CAS-protected and audit-atomic."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine,select,text,update

import test_storage
from work4ce_assistant.contracts import Work4ceError,digest
from work4ce_assistant.incident_storage import ACTIVITY_FIELDS,FIELDS,IncidentRepository
from work4ce_assistant.storage import HEAD,Store,_config,case_coordination,incident_activity,incidents_table,investigations,migrate

TENANT,OWNER='incident-tenant','source-creator'


class IncidentContract:
    @property
    def repository(self): return IncidentRepository(self.store)

    def source(self,*,tenant=TENANT,owner=OWNER,synthetic=True,evidence=None):
        identity=self.store.begin(tenant,owner)
        self.store.finish(tenant,owner,identity,{'synthetic':synthetic,'evidence':[{'evidence_id':'e1'}] if evidence is None else evidence},'completed')
        return identity

    def create(self,source_id=None,*,actor=OWNER,manage=False):
        return self.repository.create(TENANT,actor,source_id or self.source(),'Triage incident','Human context','high',manage=manage)

    def test_initial_state_detail_link_and_read_does_not_write(self):
        source=self.source()
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.for_investigation(TENANT,OWNER,source)
        queued=self.store.begin(TENANT,OWNER)
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.for_investigation(TENANT,OWNER,queued)
        with self.store.engine.connect() as connection:
            self.assertEqual(connection.execute(select(incidents_table)).all(),[])
        item=self.create(source)
        self.assertEqual(set(item),set(FIELDS))
        self.assertEqual(item['status'],'open')
        self.assertEqual(item['revision'],1)
        self.assertEqual(item['creator'],OWNER)
        self.assertEqual(item['created_by'],OWNER)
        self.assertIsNone(item['assignee'])
        self.assertEqual(self.repository.get(TENANT,OWNER,item['id']),item)
        self.assertEqual(self.repository.for_investigation(TENANT,OWNER,source),item)
        activity=self.repository.activity(TENANT,OWNER,item['id'])
        self.assertEqual(len(activity),1)
        self.assertEqual(set(activity[0]),set(ACTIVITY_FIELDS))
        self.assertEqual(activity[0]['body'],'Human context')
        self.assertEqual(activity[0]['kind'],'created')
        self.assertEqual(activity[0]['to_status'],'open')
        self.assertEqual(activity[0]['evidence_ids'],[])
        with self.assertRaisesRegex(Work4ceError,'incident_exists'):
            self.create(source)

    def test_source_incomplete_nonsynthetic_and_integrity_denied(self):
        queued=self.store.begin(TENANT,OWNER)
        for source in (queued,self.source(synthetic=False)):
            with self.assertRaisesRegex(Work4ceError,'incident_source_incomplete'):
                self.create(source)
        bad=self.source()
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id==bad).values(report='{}'))
        with self.assertRaisesRegex(Work4ceError,'incident_source_incomplete'):
            self.create(bad)
        item=self.create()
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id==item['investigation_id']).values(report='{}'))
        for operation in (lambda:self.repository.get(TENANT,OWNER,item['id']),
                          lambda:self.repository.activity(TENANT,OWNER,item['id']),
                          lambda:self.repository.add_note(TENANT,OWNER,item['id'],1,'Must not append'),
                          lambda:self.repository.list(TENANT,OWNER)):
            with self.assertRaisesRegex(Work4ceError,'incident_report_mismatch'):
                operation()

    def test_creator_assignee_scope_reassignment_revokes_created_by_access(self):
        source=self.source()
        self.store.mutate_case(TENANT,OWNER,source,0,'assign',assignee='analyst-one')
        item=self.create(source,actor='analyst-one')
        self.assertEqual(item['creator'],OWNER)
        self.assertEqual(item['created_by'],'analyst-one')
        self.assertEqual(item['assignee'],'analyst-one')
        self.store.mutate_case(TENANT,OWNER,source,1,'assign',assignee='analyst-two')
        for read in (lambda:self.repository.get(TENANT,'analyst-one',item['id']),
                     lambda:self.repository.activity(TENANT,'analyst-one',item['id']),
                     lambda:self.repository.for_investigation(TENANT,'analyst-one',source),
                     lambda:self.repository.add_note(TENANT,'analyst-one',item['id'],1,'Revoked')):
            with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
                read()
        self.assertEqual(self.repository.list(TENANT,'analyst-one'),[])
        self.assertEqual(self.repository.get(TENANT,'analyst-two',item['id'])['assignee'],'analyst-two')
        self.assertEqual(self.repository.get(TENANT,OWNER,item['id'])['created_by'],'analyst-one')
        self.assertEqual(self.repository.get(TENANT,'reviewer',item['id'],all_cases=True)['id'],item['id'])
        self.assertEqual(len(self.repository.list(TENANT,'reviewer',all_cases=True)),1)
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.get('foreign',OWNER,item['id'],all_cases=True)
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.get(TENANT,'outsider',item['id'])
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.transition(TENANT,'reviewer',item['id'],1,'in_progress')

    def test_legal_lifecycle_notes_resolution_close_and_reopen(self):
        item=self.create()
        identity=item['id']
        self.repository.transition(TENANT,OWNER,identity,1,'in_progress')
        self.repository.add_note(TENANT,OWNER,identity,2,'  Source event observed  ',['e1'])
        resolved=self.repository.transition(TENANT,OWNER,identity,3,'resolved','  Investigation disposition  ')
        self.assertEqual(resolved['resolution_note'],'Investigation disposition')
        self.assertEqual(resolved['resolved_by'],OWNER)
        with self.assertRaisesRegex(Work4ceError,'incident_management_required'):
            self.repository.transition(TENANT,OWNER,identity,4,'closed','Manager closure required')
        closed=self.repository.transition(TENANT,'manager',identity,4,'closed','Closure approved',manage=True)
        self.assertEqual(closed['closed_by'],'manager')
        self.assertEqual(closed['resolution_note'],resolved['resolution_note'])
        with self.assertRaisesRegex(Work4ceError,'incident_closed'):
            self.repository.add_note(TENANT,OWNER,identity,5,'Closed cannot append')
        with self.assertRaisesRegex(Work4ceError,'incident_management_required'):
            self.repository.transition(TENANT,OWNER,identity,5,'open','Request more context')
        reopened=self.repository.transition(TENANT,'manager',identity,5,'open','Reopen authorized',manage=True)
        self.assertIsNone(reopened['resolution_note'])
        self.assertIsNone(reopened['resolved_by'])
        self.assertIsNone(reopened['closed_at'])
        history=self.repository.activity(TENANT,OWNER,identity)
        self.assertEqual([entry['sequence'] for entry in history],[1,2,3,4,5,6])
        self.assertEqual(history[2]['body'],'Source event observed')
        self.assertEqual(history[2]['evidence_ids'],['e1'])
        self.assertEqual(history[4]['actor'],'manager')
        self.assertEqual(history[-1]['to_status'],'open')

    def test_invalid_transitions_pending_escalation_and_reopen(self):
        item=self.create()
        identity=item['id']
        for status in ('open','closed'):
            with self.assertRaisesRegex(Work4ceError,'incident_transition_invalid'):
                self.repository.transition(TENANT,OWNER,identity,1,status,'Invalid direct transition')
        with self.assertRaisesRegex(Work4ceError,'invalid_incident_update'):
            self.repository.transition(TENANT,OWNER,identity,1,'resolved',' ')
        source=item['investigation_id']
        self.store.mutate_case(TENANT,OWNER,source,0,'escalate',reason='Management required')
        with self.assertRaisesRegex(Work4ceError,'incident_escalation_pending'):
            self.repository.transition(TENANT,OWNER,identity,1,'resolved','Cannot bypass escalation')
        self.store.mutate_case(TENANT,'manager',source,1,'acknowledge',manage=True)
        self.repository.transition(TENANT,OWNER,identity,1,'resolved','Resolved after acknowledgement')
        self.store.mutate_case(TENANT,OWNER,source,2,'escalate',reason='Additional issue')
        with self.assertRaisesRegex(Work4ceError,'incident_escalation_pending'):
            self.repository.transition(TENANT,'manager',identity,2,'closed','Still escalated',manage=True)
        reopened=self.repository.transition(TENANT,OWNER,identity,2,'open','Continue review')
        self.assertEqual(reopened['status'],'open')
        self.assertIsNone(reopened['resolution_note'])

    def test_evidence_and_raw_text_bounds_are_strict(self):
        source=self.source()
        for title,description,severity in [(' '*201,'','low'),('Title','x'*2001,'low'),('','','low'),
                ('Title','','unknown'),('Title','',True)]:
            with self.assertRaisesRegex(Work4ceError,'invalid_incident_update'):
                self.repository.create(TENANT,OWNER,source,title,description,severity)
        item=self.create(source)
        for invalid_id in (None,[],True,'x'*201):
            with self.assertRaisesRegex(Work4ceError,'invalid_incident_update'):
                self.repository.get(TENANT,OWNER,invalid_id)
        for ids in (['forged'],['e1','e1'],['e1']*11,[True],['x'*129],'e1'):
            with self.assertRaisesRegex(Work4ceError,'invalid_incident_evidence'):
                self.repository.add_note(TENANT,OWNER,item['id'],1,'Context',ids)
        for revision in (0,True,1.5,201,'1'):
            with self.assertRaisesRegex(Work4ceError,'invalid_incident_update'):
                self.repository.add_note(TENANT,OWNER,item['id'],revision,'Context')
        for body in ('',' ',' '*2001):
            with self.assertRaisesRegex(Work4ceError,'invalid_incident_update'):
                self.repository.add_note(TENANT,OWNER,item['id'],1,body)
        self.assertEqual(self.repository.get(TENANT,OWNER,item['id'])['revision'],1)
        for limit in (0,101,True):
            with self.assertRaisesRegex(Work4ceError,'invalid_incident_update'):
                self.repository.list(TENANT,OWNER,limit=limit)
        unicode_id='\u2603'*128
        unicode_source=self.source(evidence=[{'evidence_id':unicode_id}])
        unicode_item=self.create(unicode_source)
        self.repository.add_note(TENANT,OWNER,unicode_item['id'],1,'Unicode source ID',[unicode_id])
        self.assertEqual(self.repository.activity(TENANT,OWNER,unicode_item['id'])[-1]['evidence_ids'],[unicode_id])

    def test_revision_and_history_limit_are_durable(self):
        item=self.create()
        identity=item['id']
        self.repository.add_note(TENANT,OWNER,identity,1,'First note')
        with self.assertRaisesRegex(Work4ceError,'incident_revision_conflict'):
            self.repository.add_note(TENANT,OWNER,identity,1,'Stale note')
        for revision in range(2,200):
            self.repository.add_note(TENANT,OWNER,identity,revision,'Bounded note '+str(revision))
        self.assertEqual(len(self.repository.activity(TENANT,OWNER,identity)),200)
        with self.assertRaisesRegex(Work4ceError,'incident_history_limit'):
            self.repository.add_note(TENANT,OWNER,identity,200,'Over budget')
        with self.assertRaisesRegex(Work4ceError,'incident_history_limit'):
            self.repository.transition(TENANT,OWNER,identity,200,'in_progress')
        self.store.close()
        self.store=Store(self.database)
        self.assertEqual(self.repository.get(TENANT,OWNER,identity)['revision'],200)
        self.assertEqual(len(self.repository.activity(TENANT,OWNER,identity)),200)

    def test_atomic_create_note_and_activity_audit_rollback(self):
        source=self.source()
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.create(source)
        self.assertEqual(self.repository.list(TENANT,OWNER),[])
        item=self.create(source)
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.repository.add_note(TENANT,OWNER,item['id'],1,'Must roll back',['e1'])
        self.assertEqual(self.repository.get(TENANT,OWNER,item['id']),item)
        self.assertEqual(len(self.repository.activity(TENANT,OWNER,item['id'])),1)
        audit=[r for r in self.store.audit_rows(TENANT) if r[0].startswith('incident.')]
        self.assertEqual(audit,[('incident.create',item['id'],'revision:1')])

    def test_corrupt_record_and_activity_fail_closed(self):
        item=self.create()
        with self.store.engine.begin() as connection:
            connection.execute(update(incidents_table).where(incidents_table.c.id==item['id']).values(resolved_by='forged'))
        with self.assertRaisesRegex(Work4ceError,'incident_integrity_failure'):
            self.repository.get(TENANT,OWNER,item['id'])
        with self.assertRaisesRegex(Work4ceError,'incident_not_found'):
            self.repository.get(TENANT,'outsider',item['id'])
        other=self.create()
        with self.store.engine.begin() as connection:
            connection.execute(update(incident_activity).where(incident_activity.c.incident_id==other['id']).values(evidence_ids='["forged"]'))
        with self.assertRaisesRegex(Work4ceError,'incident_integrity_failure'):
            self.repository.activity(TENANT,OWNER,other['id'])
        with self.assertRaisesRegex(Work4ceError,'incident_integrity_failure'):
            self.repository.add_note(TENANT,OWNER,other['id'],1,'Must fail')

    def test_multiquery_reads_keep_consistent_snapshot_during_other_store_commit(self):
        writer=Store(self.database)
        try:
            for operation in ('get','for_investigation','activity'):
                item=self.create()
                repository=self.repository
                original=repository._history
                committed=False
                def write_between_record_and_history(connection,record,report):
                    nonlocal committed
                    if not committed:
                        IncidentRepository(writer).add_note(TENANT,OWNER,item['id'],1,'Committed during reader')
                        committed=True
                    return original(connection,record,report)
                with patch.object(repository,'_history',side_effect=write_between_record_and_history):
                    if operation=='get':
                        read=repository.get(TENANT,OWNER,item['id'])
                    elif operation=='for_investigation':
                        read=repository.for_investigation(TENANT,OWNER,item['investigation_id'])
                    else:
                        read=repository.activity(TENANT,OWNER,item['id'])
                self.assertTrue(committed)
                if operation=='activity':
                    self.assertEqual(len(read),1)
                    self.assertEqual(read[0]['kind'],'created')
                else:
                    self.assertEqual(read['revision'],1)
                self.assertEqual(self.repository.get(TENANT,OWNER,item['id'])['revision'],2)
        finally:
            writer.close()

    def test_current_resolution_must_match_recorded_status_activity(self):
        item=self.create()
        self.repository.transition(TENANT,OWNER,item['id'],1,'resolved','Original disposition')
        with self.store.engine.begin() as connection:
            connection.execute(update(incidents_table).where(incidents_table.c.id==item['id']).values(resolution_note='Contradictory disposition'))
        with self.assertRaisesRegex(Work4ceError,'incident_integrity_failure'):
            self.repository.get(TENANT,OWNER,item['id'])
        with self.assertRaisesRegex(Work4ceError,'incident_integrity_failure'):
            self.repository.add_note(TENANT,OWNER,item['id'],2,'Must not conceal corruption')

    def test_report_workflow_review_and_case_remain_unchanged(self):
        work=self.store.create_workflow(TENANT,OWNER,'PowerShell',20,'source-report',review_required=True)
        identity=work['id']
        self.store.claim_workflow(TENANT,OWNER,identity,'worker')
        self.store.reserve_tool_call(TENANT,OWNER,identity,'worker')
        self.store.checkpoint_workflow(TENANT,OWNER,identity,'worker',{})
        self.store.finish_workflow(TENANT,OWNER,identity,'worker',{'synthetic':True,'evidence':[{'evidence_id':'e1'}]},'completed')
        self.store.mutate_case(TENANT,OWNER,identity,0,'assign',assignee='analyst')
        before=(self.store.get(TENANT,identity),self.store.get_workflow(TENANT,OWNER,identity),self.store.get_case(TENANT,OWNER,identity))
        item=self.create(identity,actor='analyst')
        self.repository.add_note(TENANT,'analyst',item['id'],1,'Human note',['e1'])
        self.repository.transition(TENANT,'analyst',item['id'],2,'resolved','Human disposition')
        after=(self.store.get(TENANT,identity),self.store.get_workflow(TENANT,OWNER,identity),self.store.get_case(TENANT,OWNER,identity))
        self.assertEqual(before,after)

    def test_list_order_limit_and_no_cross_owner_data(self):
        items=[self.create() for _ in range(3)]
        foreign=self.source(owner='other-owner')
        other=self.create(foreign,actor='other-owner')
        with self.store.engine.begin() as connection:
            connection.execute(update(incidents_table).where(incidents_table.c.tenant==TENANT).values(updated_at='2026-01-01T00:00:00+00:00'))
        listed=self.repository.list(TENANT,OWNER,limit=2)
        self.assertEqual([r['id'] for r in listed],sorted([i['id'] for i in items],reverse=True)[:2])
        self.assertTrue(all(set(r)==set(FIELDS) for r in listed))
        self.assertEqual(len(self.repository.list(TENANT,'reviewer',all_cases=True)),4)
        self.assertEqual(self.repository.list('foreign',OWNER,all_cases=True),[])
        self.assertNotIn(other['id'],[r['id'] for r in self.repository.list(TENANT,OWNER)])

    def test_two_store_duplicate_creation_and_cas_have_one_winner(self):
        source=self.source()
        clients=[Store(self.database),Store(self.database)]
        barrier=threading.Barrier(2)
        def create(client):
            barrier.wait(timeout=5)
            try:
                return IncidentRepository(client).create(TENANT,OWNER,source,'Concurrent','Context','low')['id']
            except Work4ceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes=[f.result(timeout=15) for f in [executor.submit(create,client) for client in clients]]
            self.assertEqual(outcomes.count('incident_exists'),1)
            identity=self.repository.list(TENANT,OWNER)[0]['id']
            barrier=threading.Barrier(2)
            def note(client,body):
                barrier.wait(timeout=5)
                try:
                    return IncidentRepository(client).add_note(TENANT,OWNER,identity,1,body)['revision']
                except Work4ceError as error:
                    return error.code
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes=[f.result(timeout=15) for f in [executor.submit(note,client,'note-'+str(index)) for index,client in enumerate(clients)]]
            self.assertCountEqual(outcomes,[2,'incident_revision_conflict'])
            self.assertEqual(len(self.repository.activity(TENANT,OWNER,identity)),2)
        finally:
            for client in clients:
                client.close()


class SQLiteIncidentTests(IncidentContract,unittest.TestCase):
    def setUp(self): test_storage.SQLiteStoreTests.setUp(self)
    def tearDown(self): test_storage.SQLiteStoreTests.tearDown(self)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'),'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL incident storage unrun')
class PostgreSQLIncidentTests(IncidentContract,unittest.TestCase):
    def setUp(self): test_storage.PostgreSQLStoreTests.setUp(self)
    def tearDown(self): test_storage.PostgreSQLStoreTests.tearDown(self)


class IncidentMigrationTests(unittest.TestCase):
    def test_v5_coordination_and_report_preserved_without_implicit_incidents(self):
        with tempfile.TemporaryDirectory() as directory:
            database=str(Path(directory)/'version-five.db')
            engine=create_engine('sqlite:///'+database)
            with engine.begin() as connection:
                command.upgrade(_config(connection),'0005_cases')
                connection.execute(investigations.insert().values(id='source-v5',tenant=TENANT,subject=OWNER,
                    status='completed',report='{"synthetic":true}',report_hash=digest({'synthetic':True}),created_at='past',updated_at='past'))
                connection.execute(case_coordination.insert().values(investigation_id='source-v5',tenant=TENANT,assignee='analyst',
                    escalation_state='none',revision=1,updated_by=OWNER,updated_at='2026-01-01T00:00:00+00:00'))
            engine.dispose()
            migrate(database)
            migrate(database)
            store=Store(database)
            self.addCleanup(store.close)
            self.assertEqual(store.get(TENANT,'source-v5')['report'],{'synthetic':True})
            self.assertEqual(store.get_case(TENANT,'analyst','source-v5')['assignee'],'analyst')
            self.assertEqual(IncidentRepository(store).list(TENANT,'analyst'),[])
            self.assertEqual(IncidentRepository(store).create(TENANT,'analyst','source-v5','Migrated source','','low')['creator'],OWNER)
            with store.engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),HEAD)
