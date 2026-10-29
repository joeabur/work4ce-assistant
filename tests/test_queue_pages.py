"""Immutable operational queue anchors retain current scoped authorization."""
import base64
import json
import os
import unittest

from sqlalchemy import update

import test_storage
from work4ce_assistant.contracts import Work4ceError,digest
from work4ce_assistant.incident_storage import FIELDS,IncidentRepository
from work4ce_assistant.pagination import (decode_history_cursor,decode_queue_cursor,encode_history_cursor,encode_queue_cursor)
from work4ce_assistant.storage import case_coordination,incident_activity,incident_investigations,incidents_table,investigations

TENANT,OWNER='queue-tenant','owner'
STAMP='2026-01-01T00:00:00.120000+00:00'
CASE_FIELDS={'investigation_id','creator','assignee','escalation_state','escalation_reason','escalated_by','escalated_at',
             'acknowledged_by','acknowledged_at','revision','updated_by','updated_at'}


def encoded(value):
    return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).decode().rstrip('=')


class QueuePagesContract:
    @property
    def repository(self): return IncidentRepository(self.store)

    def source(self,*,owner=OWNER,assignee=None):
        identity=self.store.begin(TENANT,owner)
        self.store.finish(TENANT,owner,identity,{'synthetic':True,'evidence':[{'evidence_id':'same'}]},'completed')
        self.store.mutate_case(TENANT,owner,identity,0,'assign',assignee=assignee)
        return identity

    def make(self,*,owner=OWNER,assignee=None,tied=True):
        source=self.source(owner=owner,assignee=assignee)
        item=self.repository.create(TENANT,owner,source,'Queue incident','Human context','high')
        if tied:
            # Preserve all creation metadata invariants while tying both queue anchors.
            with self.store.engine.begin() as connection:
                connection.execute(update(investigations).where(investigations.c.id==source).values(created_at=STAMP))
                connection.execute(update(case_coordination).where(case_coordination.c.investigation_id==source).values(updated_at=STAMP))
                connection.execute(update(incidents_table).where(incidents_table.c.id==item['id']).values(created_at=STAMP,updated_at=STAMP))
                connection.execute(update(incident_investigations).where(incident_investigations.c.incident_id==item['id']).values(linked_at=STAMP))
                connection.execute(update(incident_activity).where(incident_activity.c.incident_id==item['id']).values(created_at=STAMP))
        return source,item['id']

    def page(self,kind,**kwargs):
        if kind=='cases':
            return self.store.page_cases(TENANT,OWNER,**kwargs)
        return self.repository.page(TENANT,OWNER,**kwargs)

    @staticmethod
    def identities(kind,items):
        return [item['investigation_id' if kind=='cases' else 'id'] for item in items]

    def remaining(self,kind,cursor,*,limit=2):
        values=[]
        while cursor:
            page=self.page(kind,cursor=cursor,limit=limit)
            values.extend(self.identities(kind,page['items']))
            cursor=page['next_cursor']
            self.assertLess(len(values),20)
        return values

    def test_equal_timestamp_three_page_coverage_and_exact_anchors(self):
        rows=[self.make() for _ in range(7)]
        for kind,column in [('cases',0),('incidents',1)]:
            first=self.page(kind,limit=3)
            payload=json.loads(base64.urlsafe_b64decode(first['next_cursor']+'='*(-len(first['next_cursor'])%4)))
            self.assertEqual(payload['created_at'],STAMP)
            self.assertEqual(payload['kind'],kind)
            values=self.identities(kind,first['items'])+self.remaining(kind,first['next_cursor'],limit=3)
            self.assertEqual(values,sorted([row[column] for row in rows],reverse=True))
            self.assertEqual(len(set(values)),7)
            for item in first['items']:
                self.assertEqual(set(item),CASE_FIELDS if kind=='cases' else set(FIELDS))
                self.assertNotIn('anchor_created_at',item)

    def test_state_edits_do_not_move_creation_order_but_legacy_arrays_keep_updated_order(self):
        rows=[self.make() for _ in range(5)]
        case_page=self.page('cases',limit=2)
        incident_page=self.page('incidents',limit=2)
        case_anchor=case_page['items'][-1]
        incident_anchor=incident_page['items'][-1]
        self.store.mutate_case(TENANT,OWNER,case_anchor['investigation_id'],1,'escalate',reason='Updated after first page')
        self.repository.add_note(TENANT,OWNER,incident_anchor['id'],1,'Updated after first page')
        case_values=self.identities('cases',case_page['items'])+self.remaining('cases',case_page['next_cursor'])
        incident_values=self.identities('incidents',incident_page['items'])+self.remaining('incidents',incident_page['next_cursor'])
        self.assertEqual(case_values,sorted([row[0] for row in rows],reverse=True))
        self.assertEqual(incident_values,sorted([row[1] for row in rows],reverse=True))
        self.assertEqual(self.store.list_cases(TENANT,OWNER)[0]['investigation_id'],case_anchor['investigation_id'])
        self.assertEqual(self.repository.list(TENANT,OWNER)[0]['id'],incident_anchor['id'])
        self.assertIsInstance(self.store.list_cases(TENANT,OWNER),list)
        self.assertIsInstance(self.repository.list(TENANT,OWNER),list)

    def test_newer_inserts_do_not_repeat_or_shift_continuations(self):
        rows=[self.make() for _ in range(5)]
        first={kind:self.page(kind,limit=2) for kind in ('cases','incidents')}
        newer=self.make(tied=False)
        for kind,column in [('cases',0),('incidents',1)]:
            loaded=self.identities(kind,first[kind]['items'])+self.remaining(kind,first[kind]['next_cursor'])
            self.assertEqual(loaded,sorted([row[column] for row in rows],reverse=True))
            self.assertNotIn(newer[column],loaded)
            self.assertEqual(self.identities(kind,self.page(kind,limit=1)['items']),[newer[column]])

    def test_empty_exact_final_pages_and_bounds(self):
        for kind in ('cases','incidents'):
            self.assertEqual(self.page(kind),{'items':[],'next_cursor':None})
        for _ in range(4): self.make()
        for kind in ('cases','incidents'):
            self.assertIsNone(self.page(kind,limit=4)['next_cursor'])
            first=self.page(kind,limit=2)
            final=self.page(kind,limit=2,cursor=first['next_cursor'])
            self.assertEqual(len(final['items']),2)
            self.assertIsNone(final['next_cursor'])
            anchor=final['items'][-1]
            identity=anchor['investigation_id' if kind=='cases' else 'id']
            cursor=encode_queue_cursor(kind,TENANT,OWNER,STAMP,identity)
            self.assertEqual(self.page(kind,cursor=cursor),{'items':[],'next_cursor':None})
            for limit in (0,101,True,'50'):
                with self.assertRaises(Work4ceError): self.page(kind,limit=limit)
            with self.assertRaises(Work4ceError): self.page(kind,all_cases='true')

    def test_strict_cursor_kind_scope_and_history_compatibility(self):
        row=self.make()
        self.make()
        history=encode_history_cursor(TENANT,OWNER,STAMP,row[0])
        self.assertEqual(decode_history_cursor(history,TENANT,OWNER),(STAMP,row[0]))
        self.assertEqual(set(json.loads(base64.urlsafe_b64decode(history+'='*(-len(history)%4)))),{'v','scope','created_at','id'})
        for kind in ('cases','incidents'):
            valid=self.page(kind,limit=1)['next_cursor']
            payload=json.loads(base64.urlsafe_b64decode(valid+'='*(-len(valid)%4)))
            self.assertEqual(decode_queue_cursor(valid,kind,TENANT,OWNER),(STAMP,payload['id']))
            invalid=['',True,[], 'x'*513,'a','invalid+encoding','invalid/encoding',valid+'=',history,
                encoded([]),encoded({**payload,'v':2}),encoded({**payload,'v':True}),encoded({**payload,'kind':'reviews'}),
                encoded({**payload,'extra':True}),encoded({**payload,'id':'invalid'}),encoded({**payload,'id':None}),
                encoded({**payload,'created_at':'2026-01-01T00:00:00'}),encoded({**payload,'created_at':'2026-99-01T00:00:00+00:00'}),
                encoded({**payload,'scope':None})]
            duplicate='{"v":1,"v":1,"kind":'+json.dumps(kind)+',"scope":'+json.dumps(payload['scope'])+',"created_at":'+json.dumps(STAMP)+',"id":'+json.dumps(payload['id'])+'}'
            invalid.append(base64.urlsafe_b64encode(duplicate.encode()).decode().rstrip('='))
            other=self.page('incidents' if kind=='cases' else 'cases',limit=1)['next_cursor']
            invalid.append(other)
            for cursor in invalid:
                with self.subTest(kind=kind,cursor=cursor),self.assertRaisesRegex(Work4ceError,'invalid_queue_cursor') as caught:
                    self.page(kind,cursor=cursor)
                self.assertEqual(caught.exception.status,422)
            for tenant,subject in [('foreign',OWNER),(TENANT,'other'),(TENANT,None)]:
                with self.assertRaisesRegex(Work4ceError,'invalid_queue_cursor'):
                    decode_queue_cursor(valid,kind,tenant,subject)
            with self.assertRaisesRegex(Work4ceError,'invalid_queue_cursor'):
                self.page(kind,cursor=valid,all_cases=True)
            with self.assertRaisesRegex(Work4ceError,'invalid_history_cursor'):
                decode_history_cursor(valid,TENANT,OWNER)
            for timestamp,identity in [('not-a-time',row[0]),(STAMP,'not-a-uuid')]:
                with self.assertRaisesRegex(Work4ceError,'queue_position_invalid') as caught:
                    encode_queue_cursor(kind,TENANT,OWNER,timestamp,identity)
                self.assertEqual(caught.exception.status,500)

    def test_forged_position_markers_never_widen_current_sql_scope(self):
        own=self.make()
        self.make(owner='other-owner')
        for kind,column in [('cases',0),('incidents',1)]:
            forged=encoded({'v':1,'kind':kind,'scope':digest({'kind':kind,'tenant':TENANT,'subject':OWNER}),
                'created_at':'9999-01-01T00:00:00+00:00','id':'ffffffff-ffff-ffff-ffff-ffffffffffff'})
            items=self.page(kind,cursor=forged)['items']
            self.assertEqual(self.identities(kind,items),[own[column]])
            self.assertEqual(items[0]['creator'],OWNER)
            self.assertEqual(len(self.page(kind,all_cases=True)['items']),2)
            with self.assertRaisesRegex(Work4ceError,'invalid_queue_cursor'):
                if kind=='cases': self.store.page_cases('foreign',OWNER,cursor=forged)
                else: self.repository.page('foreign',OWNER,cursor=forged)

    def test_case_assignment_revocation_is_rechecked_on_next_page(self):
        rows=[self.make(owner='other-owner',assignee=OWNER) for _ in range(3)]
        ordered=sorted([row[0] for row in rows],reverse=True)
        first=self.page('cases',limit=1)
        self.assertEqual(self.identities('cases',first['items']),ordered[:1])
        self.store.mutate_case(TENANT,'other-owner',ordered[1],1,'assign',assignee=None)
        remainder=self.remaining('cases',first['next_cursor'])
        self.assertEqual(remainder,[ordered[2]])
        self.assertNotIn(ordered[1],remainder)

    def test_incident_all_source_revocation_and_hidden_groups_before_limit(self):
        rows=[self.make() for _ in range(3)]
        ordered=sorted([row[1] for row in rows],reverse=True)
        target=ordered[1]
        secondary=self.source(owner='secondary-owner',assignee=OWNER)
        self.repository.link_investigation(TENANT,OWNER,target,1,secondary,'Correlated source')
        first=self.page('incidents',limit=1)
        self.assertEqual(self.identities('incidents',first['items']),ordered[:1])
        self.store.mutate_case(TENANT,'secondary-owner',secondary,1,'assign',assignee=None)
        self.assertEqual(self.remaining('incidents',first['next_cursor']),[ordered[2]])
        # A newer inaccessible group must be filtered before the page limit.
        hidden_source,hidden=self.make(tied=False)
        private=self.source(owner='private-owner')
        self.repository.link_investigation(TENANT,'manager',hidden,1,private,'Private correlation',manage=True)
        own_page=self.page('incidents',limit=1)
        self.assertEqual(self.identities('incidents',own_page['items']),ordered[:1])
        self.assertNotIn(hidden,self.identities('incidents',own_page['items']))
        self.assertEqual(self.identities('incidents',self.page('incidents',all_cases=True,limit=1)['items']),[hidden])

    def test_page_projection_privacy_and_selected_source_integrity(self):
        rows=[self.make() for _ in range(2)]
        for kind in ('cases','incidents'):
            page=self.page(kind,limit=1)
            self.assertEqual(set(page),{'items','next_cursor'})
            self.assertNotIn('report_hash',page['items'][0])
            self.assertNotIn('review_id',page['items'][0])
            self.assertNotIn('approval_id',page['items'][0])
            self.assertNotIn('report',page['items'][0])
        newest=max(rows,key=lambda row:row[1])
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id==newest[0]).values(report='{}'))
        with self.assertRaisesRegex(Work4ceError,'incident_report_mismatch'):
            self.page('incidents',limit=1)


class SQLiteQueuePagesTests(QueuePagesContract,unittest.TestCase):
    def setUp(self): test_storage.SQLiteStoreTests.setUp(self)
    def tearDown(self): test_storage.SQLiteStoreTests.tearDown(self)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'),'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL queue pages unrun')
class PostgreSQLQueuePagesTests(QueuePagesContract,unittest.TestCase):
    def setUp(self): test_storage.PostgreSQLStoreTests.setUp(self)
    def tearDown(self): test_storage.PostgreSQLStoreTests.tearDown(self)
