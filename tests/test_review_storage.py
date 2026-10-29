"""Human decisions and single-use, synthetic-only response consumption contracts."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine, select, text, update

import test_storage
from work4ce_assistant.contracts import Work4ceError, canonical, digest
from work4ce_assistant.storage import HEAD, Store, _config, investigations, migrate, report_reviews, response_approvals

TENANT, OWNER = 'review-tenant', 'analyst'
REVIEWER, APPROVER = 'independent-reviewer', 'response-approver'


class ReviewContract:
    def report(self, *, tenant=TENANT, owner=OWNER, synthetic=True):
        identity = self.store.begin(tenant,owner)
        self.store.finish(tenant,owner,identity,{'synthetic':synthetic,'evidence':[], 'findings':[]},'completed')
        return identity

    def approved_report(self, *, owner=OWNER):
        identity = self.report(owner=owner)
        review = self.store.request_review(TENANT,owner,identity)
        self.store.decide_review(TENANT,REVIEWER,identity,review['review_id'],'approved')
        return identity

    def response(self, report_id=None, *, owner=OWNER):
        return self.store.create_response(TENANT,owner,report_id or self.approved_report(owner=owner),
            'endpoint.isolate','demo-host-1',{'duration_minutes':15})

    def approved_response(self, report_id=None):
        row = self.response(report_id)
        return self.store.decide_response(TENANT,APPROVER,row['id'],'approved')

    def test_required_review_gates_public_status_without_changing_execution_or_report(self):
        work = self.store.create_workflow(TENANT,OWNER,'PowerShell',20,'required',review_required=True)
        identity = work['id']
        self.store.claim_workflow(TENANT,OWNER,identity,'worker')
        self.store.reserve_tool_call(TENANT,OWNER,identity,'worker')
        self.store.checkpoint_workflow(TENANT,OWNER,identity,'worker',{'events':[]})
        original = {'synthetic':True,'evidence':[], 'findings':[]}
        self.store.finish_workflow(TENANT,OWNER,identity,'worker',original,'completed')
        public = self.store.get(TENANT,identity)
        self.assertEqual(public['status'],'awaiting_review')
        self.assertEqual(public['review']['state'],'pending')
        self.assertEqual(public['report'],original)
        self.assertEqual(self.store.get_workflow(TENANT,OWNER,identity)['state'],'completed')
        approved = self.store.decide_review(TENANT,REVIEWER,identity,public['review']['review_id'],'approved','Evidence reviewed')
        self.assertEqual(self.store.get(TENANT,identity)['status'],'completed')
        self.assertEqual(self.store.get(TENANT,identity)['report'],original)
        self.assertEqual(approved['report_hash'],digest(original))
        with self.assertRaisesRegex(Work4ceError,'idempotency_conflict'):
            self.store.create_workflow(TENANT,OWNER,'PowerShell',20,'required')
        legacy = self.report()
        self.assertNotIn('review',self.store.get(TENANT,legacy))

    def test_review_decision_separation_expiry_rotation_and_terminal_rejection(self):
        identity = self.report()
        first = self.store.request_review(TENANT,OWNER,identity)
        with self.assertRaisesRegex(Work4ceError,'reviewed_report_immutable'):
            self.store.finish(TENANT,OWNER,identity,{'synthetic':True,'changed':True},'completed')
        self.assertEqual(self.store.request_review(TENANT,OWNER,identity)['review_id'],first['review_id'])
        with self.assertRaisesRegex(Work4ceError,'separation_of_duties'):
            self.store.decide_review(TENANT,OWNER,identity,first['review_id'],'approved')
        with self.store.engine.begin() as connection:
            connection.execute(update(report_reviews).where(report_reviews.c.investigation_id == identity).values(expires_at=time.time()-1))
        with self.assertRaisesRegex(Work4ceError,'review_expired'):
            self.store.decide_review(TENANT,REVIEWER,identity,first['review_id'],'approved')
        renewed = self.store.request_review(TENANT,OWNER,identity)
        self.assertNotEqual(renewed['review_id'],first['review_id'])
        with self.assertRaisesRegex(Work4ceError,'review_mismatch'):
            self.store.decide_review(TENANT,REVIEWER,identity,first['review_id'],'approved')
        self.store.decide_review(TENANT,REVIEWER,identity,renewed['review_id'],'rejected','Needs more evidence')
        self.assertEqual(self.store.get(TENANT,identity)['status'],'review_rejected')
        self.assertEqual(self.store.request_review(TENANT,OWNER,identity)['state'],'rejected')
        with self.assertRaisesRegex(Work4ceError,'review_terminal'):
            self.store.decide_review(TENANT,APPROVER,identity,renewed['review_id'],'approved')

    def test_review_creation_requires_owner_complete_report_and_is_atomic_with_finish(self):
        identity = self.report()
        with self.assertRaises(Work4ceError):
            self.store.request_review(TENANT,'another-owner',identity)
        pending = self.store.begin(TENANT,OWNER)
        with self.assertRaisesRegex(Work4ceError,'review_report_incomplete'):
            self.store.request_review(TENANT,OWNER,pending)
        work = self.store.create_workflow(TENANT,OWNER,'PowerShell',20,'atomic',review_required=True)
        self.store.claim_workflow(TENANT,OWNER,work['id'],'worker')
        self.store.reserve_tool_call(TENANT,OWNER,work['id'],'worker')
        self.store.checkpoint_workflow(TENANT,OWNER,work['id'],'worker',{})
        original_audit = self.store._audit
        def fail_review(connection,tenant,subject,action,target,outcome):
            if action == 'review.request':
                raise RuntimeError('controlled audit failure')
            return original_audit(connection,tenant,subject,action,target,outcome)
        with patch.object(self.store,'_audit',side_effect=fail_review), self.assertRaises(RuntimeError):
            self.store.finish_workflow(TENANT,OWNER,work['id'],'worker',{'synthetic':True},'completed')
        self.assertEqual(self.store.get(TENANT,work['id'])['status'],'running')
        self.assertEqual(self.store.get_workflow(TENANT,OWNER,work['id'])['state'],'collected')
        with self.assertRaisesRegex(Work4ceError,'review_not_found'):
            self.store.get_review(TENANT,work['id'])

    def test_response_requires_approved_synthetic_report_and_fixed_parameters(self):
        identity = self.report()
        with self.assertRaises(Work4ceError):
            self.response(identity)
        review = self.store.request_review(TENANT,OWNER,identity)
        with self.assertRaisesRegex(Work4ceError,'report_review_required'):
            self.response(identity)
        self.store.decide_review(TENANT,REVIEWER,identity,review['review_id'],'approved')
        # Review expiry limits the decision window, not an approved immutable report.
        with self.store.engine.begin() as connection:
            connection.execute(update(report_reviews).where(report_reviews.c.investigation_id == identity).values(expires_at=time.time()-1))
        self.assertEqual(self.response(identity)['state'],'pending')
        for action,target,parameters in [('endpoint.execute','demo-host-1',{'duration_minutes':15}),
                ('endpoint.isolate','production-host',{'duration_minutes':15}),
                ('endpoint.isolate','demo-host-1',{'duration_minutes':True}),
                ('endpoint.isolate','demo-host-1',{'duration_minutes':61}),
                ('endpoint.isolate','demo-host-1',{'duration_minutes':10,'command':'unsafe'})]:
            with self.assertRaisesRegex(Work4ceError,'invalid_response_request'):
                self.store.create_response(TENANT,OWNER,identity,action,target,parameters)
        live = self.report(synthetic=False)
        r = self.store.request_review(TENANT,OWNER,live)
        self.store.decide_review(TENANT,REVIEWER,live,r['review_id'],'approved')
        with self.assertRaisesRegex(Work4ceError,'response_requires_synthetic_report'):
            self.response(live)

    def test_approval_mismatch_separation_reuse_and_dry_run(self):
        pending = self.response()
        self.assertIsNone(pending['approval_id'])
        with self.assertRaisesRegex(Work4ceError,'approval_required'):
            self.store.consume_response(TENANT,OWNER,pending['id'],'unknown')
        with self.assertRaisesRegex(Work4ceError,'separation_of_duties'):
            self.store.decide_response(TENANT,OWNER,pending['id'],'approved')
        approved = self.store.decide_response(TENANT,APPROVER,pending['id'],'approved','Reviewed synthetic scope')
        self.assertIsInstance(approved['approval_id'],str)
        self.assertEqual(approved['expires_at'],pending['expires_at'])
        with self.assertRaisesRegex(Work4ceError,'response_terminal'):
            self.store.decide_response(TENANT,REVIEWER,pending['id'],'approved')
        for bad in ('',None,'wrong-approval'):
            with self.assertRaisesRegex(Work4ceError,'approval_mismatch'):
                self.store.consume_response(TENANT,OWNER,approved['id'],bad)
        consumed = self.store.consume_response(TENANT,OWNER,approved['id'],approved['approval_id'])
        self.assertEqual(consumed['state'],'consumed')
        self.assertIs(consumed['simulation_result']['dry_run'],True)
        self.assertIs(consumed['simulation_result']['performed'],False)
        self.assertEqual(consumed['simulation_result']['target'],'demo-host-1')
        self.assertEqual(consumed['simulation_result']['parameters'],{'duration_minutes':15})
        with self.assertRaisesRegex(Work4ceError,'approval_reused'):
            self.store.consume_response(TENANT,OWNER,approved['id'],approved['approval_id'])
        with self.assertRaisesRegex(Work4ceError,'approval_reused'):
            self.store.revoke_response(TENANT,approved['id'],OWNER)

    def test_expiry_revoke_and_rejection(self):
        pending = self.response()
        with self.store.engine.begin() as connection:
            connection.execute(update(response_approvals).where(response_approvals.c.id == pending['id']).values(expires_at=time.time()-1))
        with self.assertRaisesRegex(Work4ceError,'approval_expired'):
            self.store.decide_response(TENANT,APPROVER,pending['id'],'approved')
        self.assertEqual(self.store.revoke_response(TENANT,pending['id'],OWNER)['state'],'revoked')
        self.assertEqual(self.store.revoke_response(TENANT,pending['id'],OWNER)['state'],'revoked')
        approved = self.approved_response()
        with self.store.engine.begin() as connection:
            connection.execute(update(response_approvals).where(response_approvals.c.id == approved['id']).values(expires_at=time.time()-1))
        with self.assertRaisesRegex(Work4ceError,'approval_expired'):
            self.store.consume_response(TENANT,OWNER,approved['id'],approved['approval_id'])
        self.store.revoke_response(TENANT,approved['id'],OWNER)
        with self.assertRaisesRegex(Work4ceError,'approval_required'):
            self.store.consume_response(TENANT,OWNER,approved['id'],approved['approval_id'])
        rejected = self.response()
        rejected = self.store.decide_response(TENANT,APPROVER,rejected['id'],'rejected')
        self.assertIsNone(rejected['approval_id'])
        with self.assertRaisesRegex(Work4ceError,'approval_required'):
            self.store.consume_response(TENANT,OWNER,rejected['id'],'missing')

    def test_report_and_action_binding_and_result_integrity(self):
        approved = self.approved_response()
        with self.store.engine.begin() as connection:
            connection.execute(update(response_approvals).where(response_approvals.c.id == approved['id']).values(target='demo-host-2'))
        with self.assertRaisesRegex(Work4ceError,'response_integrity_failure'):
            self.store.consume_response(TENANT,OWNER,approved['id'],approved['approval_id'])
        other = self.approved_response()
        changed = {'synthetic':True,'evidence':[{'id':'changed'}]}
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id == other['investigation_id']).values(report=canonical(changed),report_hash=digest(changed)))
        with self.assertRaisesRegex(Work4ceError,'response_report_mismatch'):
            self.store.consume_response(TENANT,OWNER,other['id'],other['approval_id'])
        with self.assertRaisesRegex(Work4ceError,'review_report_mismatch'):
            self.store.get_review(TENANT,other['investigation_id'])
        consumed = self.approved_response()
        self.store.consume_response(TENANT,OWNER,consumed['id'],consumed['approval_id'])
        with self.store.engine.begin() as connection:
            connection.execute(update(response_approvals).where(response_approvals.c.id == consumed['id']).values(simulation_result='{}'))
        with self.assertRaisesRegex(Work4ceError,'response_integrity_failure'):
            self.store.get_response(TENANT,consumed['id'])

    def test_cross_scope_and_bounded_queues(self):
        first = self.response()
        second = self.response(owner='another-analyst')
        with self.assertRaisesRegex(Work4ceError,'response_not_found'):
            self.store.consume_response(TENANT,'another-analyst',first['id'],'unknown')
        with self.assertRaisesRegex(Work4ceError,'response_not_found'):
            self.store.get_response('another-tenant',first['id'])
        with self.assertRaises(Work4ceError):
            self.store.get_review('another-tenant',first['investigation_id'])
        self.assertEqual(len(self.store.list_reviews(TENANT)),2)
        self.assertEqual([r['id'] for r in self.store.list_responses(TENANT,requester=OWNER)],[first['id']])
        self.assertEqual(len(self.store.list_responses(TENANT)),2)
        self.assertEqual(self.store.list_reviews('another-tenant'),[])
        self.assertEqual(self.store.list_responses('another-tenant'),[])
        for invalid in (0,101,True):
            with self.assertRaisesRegex(Work4ceError,'invalid_queue_limit'):
                self.store.list_reviews(TENANT,limit=invalid)
            with self.assertRaisesRegex(Work4ceError,'invalid_queue_limit'):
                self.store.list_responses(TENANT,limit=invalid)

    def test_atomic_consumption_and_decision_audits(self):
        pending = self.response()
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.store.decide_response(TENANT,APPROVER,pending['id'],'approved')
        self.assertEqual(self.store.get_response(TENANT,pending['id'])['state'],'pending')
        self.assertIsNone(self.store.get_response(TENANT,pending['id'])['approval_id'])
        approved = self.store.decide_response(TENANT,APPROVER,pending['id'],'approved')
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.store.consume_response(TENANT,OWNER,approved['id'],approved['approval_id'])
        unchanged = self.store.get_response(TENANT,approved['id'])
        self.assertEqual(unchanged['state'],'approved')
        self.assertIsNone(unchanged['simulation_result'])
        self.assertEqual(self.store.consume_response(TENANT,OWNER,approved['id'],approved['approval_id'])['state'],'consumed')

    def test_disabled_evidence_source_blocks_final_consumption(self):
        identity = self.store.begin(TENANT,OWNER)
        self.store.finish(TENANT,OWNER,identity,{'synthetic':True,
            'evidence':[{'connector_id':'demo-rest'}]},'completed')
        review = self.store.request_review(TENANT,OWNER,identity)
        self.store.decide_review(TENANT,REVIEWER,identity,review['review_id'],'approved')
        self.store.initialize_connector(TENANT,'demo-rest')
        approved = self.approved_response(identity)
        self.store.disable(TENANT,'admin','demo-rest')
        with self.assertRaisesRegex(Work4ceError,'response_connector_unavailable'):
            self.store.consume_response(TENANT,OWNER,approved['id'],approved['approval_id'])
        self.assertEqual(self.store.get_response(TENANT,approved['id'])['state'],'approved')
        self.assertIsNone(self.store.get_response(TENANT,approved['id'])['simulation_result'])

    def test_two_stores_consume_approval_exactly_once(self):
        approved = self.approved_response()
        clients = [Store(self.database),Store(self.database)]
        barrier = threading.Barrier(2)
        def consume(client):
            barrier.wait(timeout=5)
            try:
                return client.consume_response(TENANT,OWNER,approved['id'],approved['approval_id'])['state']
            except Work4ceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = [f.result(timeout=15) for f in [executor.submit(consume,client) for client in clients]]
            self.assertCountEqual(outcomes,['consumed','approval_reused'])
            self.assertEqual(sum(action=='response.simulate' for action,_,_ in self.store.audit_rows(TENANT)),1)
        finally:
            for client in clients:
                client.close()

    def test_pending_response_quota_and_revocation_release(self):
        identity = self.approved_report()
        pending = [self.response(identity) for _ in range(100)]
        with self.assertRaisesRegex(Work4ceError,'response_queue_full') as caught:
            self.response(identity)
        self.assertEqual(caught.exception.status,429)
        self.store.revoke_response(TENANT,pending[0]['id'],OWNER)
        self.assertEqual(self.response(identity)['state'],'pending')
        self.assertEqual(len(self.store.list_responses(TENANT,requester=OWNER,limit=100)),100)


class SQLiteReviewTests(ReviewContract,unittest.TestCase):
    def setUp(self):
        test_storage.SQLiteStoreTests.setUp(self)

    def tearDown(self):
        test_storage.SQLiteStoreTests.tearDown(self)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'),'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL review storage unrun')
class PostgreSQLReviewTests(ReviewContract,unittest.TestCase):
    def setUp(self):
        test_storage.PostgreSQLStoreTests.setUp(self)

    def tearDown(self):
        test_storage.PostgreSQLStoreTests.tearDown(self)


class ReviewMigrationTests(unittest.TestCase):
    def test_v3_reports_remain_ungated_and_idempotency_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            database=str(Path(directory)/'version-three.db')
            engine=create_engine('sqlite:///'+database)
            request_hash=digest({'query':'PowerShell','limit':20,'max_tool_calls':2,'duration_seconds':120.0})
            with engine.begin() as connection:
                command.upgrade(_config(connection),'0003_models')
                connection.execute(text("INSERT INTO investigations(id,tenant,subject,status,report,report_hash,created_at,updated_at) VALUES ('v3',:tenant,:subject,'completed',:report,:hash,'past','past')"),
                    {'tenant':TENANT,'subject':OWNER,'report':'{"synthetic":true}','hash':digest({'synthetic':True})})
                connection.execute(text('INSERT INTO workflow_state(id,tenant,subject,idempotency_key,request_hash,query,"limit",max_tool_calls,tool_calls,deadline,state,revision) VALUES (:id,:tenant,:subject,:key,:hash,:query,20,2,0,:deadline,:state,0)'),
                    {'id':'v3','tenant':TENANT,'subject':OWNER,'key':'v3-key','hash':request_hash,'query':'PowerShell','deadline':time.time()+120,'state':'completed'})
            engine.dispose()
            migrate(database)
            migrate(database)
            store=Store(database)
            self.addCleanup(store.close)
            self.assertEqual(store.get(TENANT,'v3'),{'id':'v3','status':'completed','report':{'synthetic':True}})
            self.assertEqual(store.get_workflow(TENANT,OWNER,'v3')['review_required'],0)
            self.assertEqual(store.create_workflow(TENANT,OWNER,'PowerShell',20,'v3-key')['id'],'v3')
            with store.engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),HEAD)
