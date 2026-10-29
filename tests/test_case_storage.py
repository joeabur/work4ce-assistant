"""Atomic tenant-scoped case coordination, independent of report/approval state."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine, select, text, update

import test_storage
from work4ce_assistant.contracts import Work4ceError, digest
from work4ce_assistant.storage import HEAD, Store, _config, case_coordination, investigations, migrate, report_reviews

TENANT, CREATOR = 'case-tenant', 'creator'
CASE_FIELDS = {'investigation_id','creator','assignee','escalation_state','escalation_reason',
               'escalated_by','escalated_at','acknowledged_by','acknowledged_at','revision','updated_by','updated_at'}


class CaseContract:
    def create(self,*,tenant=TENANT,creator=CREATOR):
        return self.store.begin(tenant,creator)

    def mutate(self,identity,revision,operation,*,actor=CREATOR,**kwargs):
        return self.store.mutate_case(TENANT,actor,identity,revision,operation,**kwargs)

    def test_default_read_does_not_create_coordination_or_audit(self):
        identity=self.create()
        before=self.store.audit_rows(TENANT)
        first=self.store.get_case(TENANT,CREATOR,identity)
        self.assertEqual(first,{'investigation_id':identity,'creator':CREATOR,'assignee':None,
            'escalation_state':'none','escalation_reason':None,'escalated_by':None,'escalated_at':None,
            'acknowledged_by':None,'acknowledged_at':None,'revision':0,'updated_by':None,'updated_at':None})
        self.assertEqual(self.store.get_case(TENANT,CREATOR,identity),first)
        self.assertEqual(self.store.list_cases(TENANT,CREATOR),[])
        with self.store.engine.connect() as connection:
            self.assertEqual(connection.execute(select(case_coordination)).all(),[])
        self.assertEqual(self.store.audit_rows(TENANT),before)

    def test_scope_creator_assignee_manager_and_tenant_isolation(self):
        own=self.create()
        other=self.create(creator='other-creator')
        unpersisted=self.create()
        foreign=self.create(tenant='foreign-tenant')
        self.mutate(own,0,'assign',assignee='analyst')
        self.mutate(other,0,'assign',actor='other-creator',assignee='other-analyst')
        for identity,tenant,subject,all_cases in [(own,TENANT,'outsider',False),(foreign,TENANT,CREATOR,True)]:
            with self.assertRaisesRegex(Work4ceError,'case_not_found'):
                self.store.get_case(tenant,subject,identity,all_cases=all_cases)
        self.assertEqual(self.store.get_case(TENANT,'analyst',own)['creator'],CREATOR)
        self.assertEqual(self.store.get_case(TENANT,'manager',own,all_cases=True)['assignee'],'analyst')
        self.assertEqual([c['investigation_id'] for c in self.store.list_cases(TENANT,CREATOR)],[own])
        self.assertEqual([c['investigation_id'] for c in self.store.list_cases(TENANT,'analyst')],[own])
        self.assertEqual({c['investigation_id'] for c in self.store.list_cases(TENANT,'manager',all_cases=True)},{own,other})
        self.assertNotIn(unpersisted,[c['investigation_id'] for c in self.store.list_cases(TENANT,CREATOR)])
        self.assertEqual(self.store.list_cases('foreign-tenant',CREATOR,all_cases=True),[])
        with self.assertRaisesRegex(Work4ceError,'case_not_found'):
            self.store.mutate_case('foreign-tenant',CREATOR,own,1,'assign',assignee='outsider',manage=True)

    def test_reassignment_revokes_assignee_before_stale_revision_check(self):
        identity=self.create()
        self.mutate(identity,0,'assign',assignee='analyst-one')
        second=self.mutate(identity,1,'assign',actor='analyst-one',assignee='analyst-two')
        self.assertEqual(second['revision'],2)
        with self.assertRaisesRegex(Work4ceError,'case_not_found'):
            self.store.get_case(TENANT,'analyst-one',identity)
        with self.assertRaisesRegex(Work4ceError,'case_not_found'):
            self.mutate(identity,1,'escalate',actor='analyst-one',reason='Stale access')
        self.assertEqual(self.store.list_cases(TENANT,'analyst-one'),[])
        with self.assertRaisesRegex(Work4ceError,'case_revision_conflict'):
            self.mutate(identity,1,'assign',assignee=None)
        third=self.mutate(identity,2,'assign',actor='manager',assignee=None,manage=True)
        self.assertIsNone(third['assignee'])
        self.assertEqual(self.store.get_case(TENANT,CREATOR,identity)['revision'],3)

    def test_escalation_acknowledgement_and_reescalation_preserve_audit(self):
        identity=self.create()
        with self.assertRaisesRegex(Work4ceError,'case_not_escalated'):
            self.mutate(identity,0,'acknowledge',actor='manager',manage=True)
        pending=self.mutate(identity,0,'escalate',reason='  Need incident review  ')
        self.assertEqual(pending['escalation_state'],'requested')
        self.assertEqual(pending['escalation_reason'],'Need incident review')
        self.assertEqual(pending['escalated_by'],CREATOR)
        self.assertIsNone(pending['acknowledged_by'])
        with self.assertRaisesRegex(Work4ceError,'case_escalation_pending'):
            self.mutate(identity,1,'escalate',reason='Do not overwrite')
        with self.assertRaisesRegex(Work4ceError,'case_management_required'):
            self.mutate(identity,1,'acknowledge')
        acknowledged=self.mutate(identity,1,'acknowledge',actor='manager',manage=True)
        self.assertEqual(acknowledged['escalation_state'],'acknowledged')
        self.assertEqual(acknowledged['escalation_reason'],pending['escalation_reason'])
        self.assertEqual(acknowledged['escalated_at'],pending['escalated_at'])
        self.assertEqual(acknowledged['acknowledged_by'],'manager')
        self.assertIsNotNone(acknowledged['acknowledged_at'])
        again=self.mutate(identity,2,'escalate',reason='New follow-up')
        self.assertEqual(again['escalation_reason'],'New follow-up')
        self.assertEqual(again['escalation_state'],'requested')
        self.assertIsNone(again['acknowledged_by'])
        self.assertIsNone(again['acknowledged_at'])
        audit=[r for r in self.store.audit_rows(TENANT) if r[0].startswith('case.')]
        self.assertEqual(audit,[('case.escalate',identity,'revision:1'),
            ('case.acknowledge',identity,'revision:2'),('case.escalate',identity,'revision:3')])
        self.assertNotIn('Need incident review',str(audit))

    def test_invalid_fields_revisions_and_flags_do_not_persist(self):
        identity=self.create()
        for revision in (-1,True,1.5,2147483647):
            with self.assertRaisesRegex(Work4ceError,'invalid_case_update'):
                self.mutate(identity,revision,'assign',assignee='analyst')
        for operation,kwargs in [('unknown',{}),('assign',{'assignee':True}),('assign',{'assignee':''}),
            ('assign',{'assignee':'x'*257}),('assign',{'reason':'forged escalation'}),
            ('escalate',{'reason':' '}),('escalate',{'reason':'x'*1001}),('escalate',{'reason':'valid'+' '*1000}),('escalate',{'reason':True}),
            ('escalate',{'reason':'valid','assignee':'forged'}),('acknowledge',{'reason':'forged'}),
            ('assign',{'assignee':'analyst','manage':'true'})]:
            with self.subTest(operation=operation,kwargs=kwargs),self.assertRaisesRegex(Work4ceError,'invalid_case_update'):
                self.mutate(identity,0,operation,**kwargs)
        for limit in (0,101,True,'50'):
            with self.assertRaisesRegex(Work4ceError,'invalid_case_update'):
                self.store.list_cases(TENANT,CREATOR,limit=limit)
        with self.assertRaisesRegex(Work4ceError,'invalid_case_update'):
            self.store.get_case(TENANT,CREATOR,identity,all_cases='true')
        self.assertEqual(self.store.list_cases(TENANT,CREATOR),[])
        self.assertEqual(self.store.get_case(TENANT,CREATOR,identity)['revision'],0)

    def test_corrupt_metadata_fails_closed(self):
        identity=self.create()
        self.mutate(identity,0,'assign',assignee='analyst')
        with self.store.engine.begin() as connection:
            # This malformed combination passes database enums but is not a valid state.
            connection.execute(update(case_coordination).where(case_coordination.c.investigation_id == identity).values(escalated_by='unexpected'))
        with self.assertRaisesRegex(Work4ceError,'case_integrity_failure'):
            self.store.get_case(TENANT,CREATOR,identity)
        with self.assertRaisesRegex(Work4ceError,'case_integrity_failure'):
            self.store.list_cases(TENANT,CREATOR)
        with self.assertRaisesRegex(Work4ceError,'case_integrity_failure'):
            self.mutate(identity,1,'assign',assignee=None)
        with self.assertRaisesRegex(Work4ceError,'case_not_found'):
            self.store.get_case(TENANT,'outsider',identity)

    def test_restart_persistence_and_deterministic_list_order(self):
        identities=[self.create() for _ in range(3)]
        for identity in identities:
            self.mutate(identity,0,'assign',assignee='analyst')
        with self.store.engine.begin() as connection:
            connection.execute(update(case_coordination).where(case_coordination.c.tenant == TENANT).values(updated_at='2026-01-01T00:00:00+00:00'))
        before=self.store.get_case(TENANT,CREATOR,identities[0])
        self.store.close()
        self.store=Store(self.database)
        self.assertEqual(self.store.get_case(TENANT,CREATOR,identities[0]),before)
        listed=self.store.list_cases(TENANT,'analyst',limit=2)
        self.assertEqual([c['investigation_id'] for c in listed],sorted(identities,reverse=True)[:2])
        self.assertTrue(all(set(c)==CASE_FIELDS for c in listed))

    def test_report_review_and_workflow_remain_unchanged(self):
        workflow=self.store.create_workflow(TENANT,CREATOR,'PowerShell',20,'case-report',review_required=True)
        identity=workflow['id']
        self.store.claim_workflow(TENANT,CREATOR,identity,'worker')
        self.store.reserve_tool_call(TENANT,CREATOR,identity,'worker')
        self.store.checkpoint_workflow(TENANT,CREATOR,identity,'worker',{})
        self.store.finish_workflow(TENANT,CREATOR,identity,'worker',{'synthetic':True,'evidence':[]},'completed')
        report_before=self.store.get(TENANT,identity)
        workflow_before=self.store.get_workflow(TENANT,CREATOR,identity)
        with self.store.engine.connect() as connection:
            raw_before=tuple(connection.execute(select(investigations).where(investigations.c.id == identity)).one())
        self.mutate(identity,0,'assign',assignee='analyst')
        self.mutate(identity,1,'escalate',reason='Analyst handoff')
        self.mutate(identity,2,'acknowledge',actor='manager',manage=True)
        self.assertEqual(self.store.get(TENANT,identity),report_before)
        self.assertEqual(self.store.get_workflow(TENANT,CREATOR,identity),workflow_before)
        with self.store.engine.connect() as connection:
            self.assertEqual(tuple(connection.execute(select(investigations).where(investigations.c.id == identity)).one()),raw_before)

    def test_case_mutation_and_audit_are_atomic(self):
        identity=self.create()
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.mutate(identity,0,'assign',assignee='analyst')
        self.assertEqual(self.store.get_case(TENANT,CREATOR,identity)['revision'],0)
        self.mutate(identity,0,'assign',assignee='analyst')
        before=self.store.get_case(TENANT,CREATOR,identity)
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.mutate(identity,1,'escalate',reason='Must roll back')
        self.assertEqual(self.store.get_case(TENANT,CREATOR,identity),before)
        self.assertEqual(sum(action.startswith('case.') for action,_,_ in self.store.audit_rows(TENANT)),1)

    def test_two_store_compare_and_swap_has_one_winner(self):
        identity=self.create()
        clients=[Store(self.database),Store(self.database)]
        barrier=threading.Barrier(2)
        def mutate(client,assignee):
            barrier.wait(timeout=5)
            try:
                return client.mutate_case(TENANT,CREATOR,identity,0,'assign',assignee=assignee)['assignee']
            except Work4ceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures=[executor.submit(mutate,client,'analyst-'+str(index)) for index,client in enumerate(clients)]
                outcomes=[f.result(timeout=15) for f in futures]
            self.assertEqual(outcomes.count('case_revision_conflict'),1)
            self.assertEqual(self.store.get_case(TENANT,CREATOR,identity)['revision'],1)
            self.assertIn(self.store.get_case(TENANT,CREATOR,identity)['assignee'],outcomes)
            self.assertEqual(sum(action=='case.assign' for action,_,_ in self.store.audit_rows(TENANT)),1)
        finally:
            for client in clients:
                client.close()


class SQLiteCaseTests(CaseContract,unittest.TestCase):
    def setUp(self):
        test_storage.SQLiteStoreTests.setUp(self)

    def tearDown(self):
        test_storage.SQLiteStoreTests.tearDown(self)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'),'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL case storage unrun')
class PostgreSQLCaseTests(CaseContract,unittest.TestCase):
    def setUp(self):
        test_storage.PostgreSQLStoreTests.setUp(self)

    def tearDown(self):
        test_storage.PostgreSQLStoreTests.tearDown(self)


class CaseMigrationTests(unittest.TestCase):
    def test_v4_report_review_rows_are_preserved_without_coordination_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            database=str(Path(directory)/'version-four.db')
            engine=create_engine('sqlite:///'+database)
            report={'synthetic':True,'evidence':[]}
            with engine.begin() as connection:
                command.upgrade(_config(connection),'0004_reviews')
                connection.execute(investigations.insert().values(id='legacy-v4',tenant=TENANT,subject=CREATOR,
                    status='completed',report='{"evidence":[],"synthetic":true}',report_hash=digest(report),created_at='past',updated_at='past'))
                connection.execute(report_reviews.insert().values(investigation_id='legacy-v4',review_id='legacy-review',tenant=TENANT,
                    requester=CREATOR,report_hash=digest(report),state='approved',expires_at=1,reviewer='reviewer',comment='retained'))
            engine.dispose()
            migrate(database)
            migrate(database)
            store=Store(database)
            self.addCleanup(store.close)
            self.assertEqual(store.get(TENANT,'legacy-v4')['report'],report)
            self.assertEqual(store.get_review(TENANT,'legacy-v4')['comment'],'retained')
            self.assertEqual(store.get_case(TENANT,CREATOR,'legacy-v4')['revision'],0)
            self.assertEqual(store.list_cases(TENANT,CREATOR),[])
            with store.engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),HEAD)
