"""Analyst list projections preserve ownership, integrity, and private metadata."""
import json
import base64
import os
import unittest

from sqlalchemy import update

import test_storage
from work4ce_assistant.contracts import Work4ceError, digest
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


    @staticmethod
    def cursor(payload):
        return base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode().rstrip('=')

    def test_keyset_pages_cover_equal_timestamp_ties_without_duplicates(self):
        identities = [self.report(query='tie-'+str(index)) for index in range(8)]
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.tenant == TENANT).values(created_at='2026-01-01T00:00:00+00:00'))
        cursor = None
        loaded = []
        page_sizes = []
        while True:
            page = self.store.page_investigations(TENANT,subject=OWNER,limit=3,cursor=cursor)
            loaded.extend(row['id'] for row in page['items'])
            page_sizes.append(len(page['items']))
            cursor = page['next_cursor']
            if cursor is None:
                break
            self.assertLess(len(page_sizes),5)
        self.assertEqual(loaded,sorted(identities,reverse=True))
        self.assertEqual(len(set(loaded)),8)
        self.assertEqual(page_sizes,[3,3,2])

    def test_newer_insert_does_not_shift_or_repeat_loaded_history(self):
        identities = [self.report() for _ in range(5)]
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.tenant == TENANT).values(created_at='2026-01-01T00:00:00+00:00'))
        first = self.store.page_investigations(TENANT,subject=OWNER,limit=2)
        newer = self.report(query='newer-than-anchor')
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id == newer).values(created_at='2026-02-01T00:00:00+00:00'))
        loaded = [row['id'] for row in first['items']]
        cursor = first['next_cursor']
        while cursor:
            page = self.store.page_investigations(TENANT,subject=OWNER,limit=2,cursor=cursor)
            loaded.extend(row['id'] for row in page['items'])
            cursor = page['next_cursor']
        self.assertEqual(loaded,sorted(identities,reverse=True))
        self.assertNotIn(newer,loaded)
        self.assertEqual(self.store.page_investigations(TENANT,subject=OWNER,limit=1)['items'][0]['id'],newer)

    def test_empty_exact_and_final_pages(self):
        self.assertEqual(self.store.page_investigations(TENANT),{'items':[],'next_cursor':None})
        for _ in range(4):
            self.report()
        exact = self.store.page_investigations(TENANT,subject=OWNER,limit=4)
        self.assertEqual(len(exact['items']),4)
        self.assertIsNone(exact['next_cursor'])
        first = self.store.page_investigations(TENANT,subject=OWNER,limit=2)
        self.assertIsInstance(first['next_cursor'],str)
        final = self.store.page_investigations(TENANT,subject=OWNER,limit=2,cursor=first['next_cursor'])
        self.assertEqual(len(final['items']),2)
        self.assertIsNone(final['next_cursor'])
        anchor = final['items'][-1]
        cursor = self.cursor({'v':1,'scope':digest({'tenant':TENANT,'subject':OWNER}),'created_at':anchor['created_at'],'id':anchor['id']})
        self.assertEqual(self.store.page_investigations(TENANT,subject=OWNER,cursor=cursor),{'items':[],'next_cursor':None})

    def test_strict_cursor_validation_and_scope_binding(self):
        own = self.report()
        self.report()
        valid = self.store.page_investigations(TENANT,subject=OWNER,limit=1)['next_cursor']
        payload = json.loads(base64.urlsafe_b64decode(valid + '='*(-len(valid)%4)))
        malformed = ['',True,[], 'x'*513,'bad+encoding','bad/encoding', valid+'=', 'a',
            self.cursor([]),self.cursor({**payload,'v':2}),self.cursor({**payload,'v':True}),
            self.cursor({**payload,'extra':'field'}),self.cursor({**payload,'id':'not-a-uuid'}),
            self.cursor({**payload,'id':None}),self.cursor({**payload,'created_at':'2026-99-01T00:00:00+00:00'}),
            self.cursor({**payload,'created_at':'2026-01-01T00:00:00'}),self.cursor({**payload,'scope':None})]
        duplicate_json = '{"v":1,"v":1,"scope":'+json.dumps(payload['scope'])+',"created_at":'+json.dumps(payload['created_at'])+',"id":'+json.dumps(payload['id'])+'}'
        malformed.append(base64.urlsafe_b64encode(duplicate_json.encode()).decode().rstrip('='))
        for cursor in malformed:
            with self.subTest(cursor=cursor),self.assertRaisesRegex(Work4ceError,'invalid_history_cursor') as caught:
                self.store.page_investigations(TENANT,subject=OWNER,cursor=cursor)
            self.assertEqual(caught.exception.status,422)
        for tenant,subject in [('other-tenant',OWNER),(TENANT,'other-owner'),(TENANT,None)]:
            with self.assertRaisesRegex(Work4ceError,'invalid_history_cursor'):
                self.store.page_investigations(tenant,subject=subject,cursor=valid)
        # This is an unsigned position marker. A caller can fabricate a correctly
        # scoped marker, but cannot change the server's authoritative SQL scope.
        self.report(subject='other-owner')
        self.report(tenant='other-tenant')
        forged = self.cursor({**payload,'created_at':'9999-01-01T00:00:00+00:00','id':'ffffffff-ffff-ffff-ffff-ffffffffffff'})
        items = self.store.page_investigations(TENANT,subject=OWNER,cursor=forged)['items']
        self.assertEqual(len(items),2)
        self.assertTrue(all(item['subject']==OWNER for item in items))

    def test_history_projection_retains_review_privacy_and_integrity_checks(self):
        identity = self.report()
        review = self.store.request_review(TENANT,OWNER,identity)
        self.store.decide_review(TENANT,'private-reviewer',identity,review['review_id'],'approved','private comment')
        self.report()
        first = self.store.page_investigations(TENANT,subject=OWNER,limit=1)
        second = self.store.page_investigations(TENANT,subject=OWNER,limit=1,cursor=first['next_cursor'])
        items = first['items']+second['items']
        self.assertTrue(all(set(row)==SUMMARY_FIELDS for row in items))
        approved = next(row for row in items if row['id']==identity)
        self.assertEqual(approved['review_state'],'approved')
        raw = json.dumps([first,second])
        for private in ('private raw telemetry','private report metadata','private comment','private-reviewer',review['review_id']):
            self.assertNotIn(private,raw)
        self.assertEqual(self.store.list_investigations(TENANT,subject=OWNER),items)
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id == identity).values(report='{}'))
        with self.assertRaisesRegex(Work4ceError,'report_integrity_failure'):
            self.store.page_investigations(TENANT,subject=OWNER)


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
