"""Analyst list projections preserve ownership, integrity, and private metadata."""
import json
import os
import unittest

from sqlalchemy import update

import test_storage
from work4ce_assistant.contracts import Work4ceError
from work4ce_assistant.storage import investigations, report_reviews

TENANT, OWNER = 'workbench-tenant', 'analyst-one'
SUMMARY_FIELDS = {'id','subject','status','created_at','updated_at','query','assessment','evidence_count','review_state'}


class WorkbenchContract:
    def report(self, *, tenant=TENANT, subject=OWNER, query='PowerShell', **fields):
        identity = self.store.begin(tenant,subject)
        report = {'synthetic':True,'query':query,'assessment':'needs_analyst_review',
                  'evidence':[{'id':'e1','content':{'summary':'private raw telemetry'}}],
                  'secret_internal_field':'private report metadata',**fields}
        self.store.finish(tenant,subject,identity,report,'completed')
        return identity

    def test_tenant_and_owner_filters(self):
        first = self.report()
        second = self.report(subject='analyst-two')
        foreign = self.report(tenant='foreign-tenant')
        self.assertEqual({row['id'] for row in self.store.list_investigations(TENANT)}, {first,second})
        self.assertEqual([row['id'] for row in self.store.list_investigations(TENANT,subject=OWNER)], [first])
        self.assertEqual(self.store.list_investigations(TENANT,subject='unknown'), [])
        self.assertEqual([row['id'] for row in self.store.list_investigations('foreign-tenant')], [foreign])
        self.assertEqual(self.store.list_investigations('unknown-tenant'), [])
        # A corrupt foreign report cannot affect a differently scoped list.
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id == foreign).values(report='{}'))
        self.assertEqual(len(self.store.list_investigations(TENANT)), 2)

    def test_order_limit_and_validation(self):
        identities = [self.report(query='query-'+str(index)) for index in range(4)]
        dates = ['2026-01-01T00:00:00+00:00','2026-01-03T00:00:00+00:00',
                 '2026-01-03T00:00:00+00:00','2026-01-02T00:00:00+00:00']
        with self.store.engine.begin() as connection:
            for identity,date in zip(identities,dates):
                connection.execute(update(investigations).where(investigations.c.id == identity).values(created_at=date))
        expected = sorted(zip(identities,dates),key=lambda item:(item[1],item[0]),reverse=True)
        actual = self.store.list_investigations(TENANT,subject=OWNER,limit=3)
        self.assertEqual([row['id'] for row in actual], [identity for identity,_ in expected[:3]])
        self.assertEqual(len(self.store.list_investigations(TENANT,limit=1)),1)
        for invalid in (0,101,True,1.5,'10'):
            with self.assertRaisesRegex(Work4ceError,'invalid_queue_limit'):
                self.store.list_investigations(TENANT,limit=invalid)
        for invalid in ('',False,[], 'x'*257):
            with self.assertRaisesRegex(Work4ceError,'invalid_subject_filter'):
                self.store.list_investigations(TENANT,subject=invalid)

    def test_public_review_states_and_private_metadata_omission(self):
        pending,approved,rejected = self.report(),self.report(),self.report()
        pending_review = self.store.request_review(TENANT,OWNER,pending)
        approved_review = self.store.request_review(TENANT,OWNER,approved)
        rejected_review = self.store.request_review(TENANT,OWNER,rejected)
        self.store.decide_review(TENANT,'private-reviewer',approved,approved_review['review_id'],'approved','private comment')
        self.store.decide_review(TENANT,'private-reviewer',rejected,rejected_review['review_id'],'rejected','private rejection')
        rows = {row['id']:row for row in self.store.list_investigations(TENANT)}
        self.assertEqual(rows[pending]['status'],'awaiting_review')
        self.assertEqual(rows[pending]['review_state'],'pending')
        self.assertEqual(rows[approved]['status'],'completed')
        self.assertEqual(rows[approved]['review_state'],'approved')
        self.assertEqual(rows[rejected]['status'],'review_rejected')
        self.assertEqual(rows[rejected]['review_state'],'rejected')
        for row in rows.values():
            self.assertEqual(set(row),SUMMARY_FIELDS)
            self.assertEqual(row['evidence_count'],1)
            self.assertEqual(row['query'],'PowerShell')
        raw = json.dumps(list(rows.values()))
        for private in ('private raw telemetry','private report metadata','private comment','private rejection',
                        'private-reviewer',pending_review['review_id'],approved_review['review_id'],rejected_review['review_id']):
            self.assertNotIn(private,raw)

    def test_legacy_and_running_queries_and_safe_unknown_fields(self):
        legacy = self.report(query='legacy-query')
        workflow = self.store.create_workflow(TENANT,OWNER,'running-query',20,'running-case')
        empty = self.store.begin(TENANT,OWNER)
        malformed = self.report(query={'secret':'do not emit'},assessment={'secret':'do not emit'},evidence={'secret':'do not emit'})
        rows = {row['id']:row for row in self.store.list_investigations(TENANT)}
        self.assertEqual(rows[legacy]['query'],'legacy-query')
        self.assertEqual(rows[workflow['id']]['query'],'running-query')
        self.assertEqual(rows[workflow['id']]['status'],'running')
        self.assertIsNone(rows[workflow['id']]['assessment'])
        self.assertEqual(rows[workflow['id']]['evidence_count'],0)
        self.assertIsNone(rows[empty]['query'])
        self.assertIsNone(rows[malformed]['query'])
        self.assertIsNone(rows[malformed]['assessment'])
        self.assertEqual(rows[malformed]['evidence_count'],0)
        self.assertNotIn('do not emit',json.dumps(list(rows.values())))

    def test_report_integrity_fail_closed_before_deriving_summary(self):
        identity = self.report()
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id == identity).values(report='{"query":"forged"}'))
        with self.assertRaisesRegex(Work4ceError,'report_integrity_failure'):
            self.store.list_investigations(TENANT,subject=OWNER)
        self.assertEqual(self.store.list_investigations(TENANT,subject='another-owner'),[])

    def test_review_join_uses_tenant_and_checks_owner_binding(self):
        identity = self.report()
        self.store.request_review(TENANT,OWNER,identity)
        with self.store.engine.begin() as connection:
            connection.execute(update(report_reviews).where(report_reviews.c.investigation_id == identity).values(tenant='foreign-tenant'))
        row = self.store.list_investigations(TENANT)[0]
        self.assertIsNone(row['review_state'])
        self.assertEqual(row['status'],'completed')
        with self.store.engine.begin() as connection:
            connection.execute(update(report_reviews).where(report_reviews.c.investigation_id == identity).values(tenant=TENANT,requester='another-owner'))
        with self.assertRaisesRegex(Work4ceError,'review_report_mismatch'):
            self.store.list_investigations(TENANT)


class SQLiteWorkbenchTests(WorkbenchContract,unittest.TestCase):
    def setUp(self):
        test_storage.SQLiteStoreTests.setUp(self)

    def tearDown(self):
        test_storage.SQLiteStoreTests.tearDown(self)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'),'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL workbench storage unrun')
class PostgreSQLWorkbenchTests(WorkbenchContract,unittest.TestCase):
    def setUp(self):
        test_storage.PostgreSQLStoreTests.setUp(self)

    def tearDown(self):
        test_storage.PostgreSQLStoreTests.tearDown(self)
