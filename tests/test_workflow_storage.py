"""Durable workflow storage contracts on SQLite and disposable PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine, inspect, select, text, update

import test_storage
from work4ce_assistant.contracts import Work4ceError
from work4ce_assistant.storage import HEAD, Store, _config, audit_table, investigations, migrate, workflow_state

TENANT, SUBJECT = 'workflow-tenant', 'workflow-analyst'


class WorkflowContract:
    def create(self, key='request-one', **kwargs):
        return self.store.create_workflow(TENANT, SUBJECT, 'PowerShell', 20, key, **kwargs)

    def claim(self, identity, worker='worker-one', **kwargs):
        return self.store.claim_workflow(TENANT, SUBJECT, identity, worker, **kwargs)

    def test_idempotency_and_scope(self):
        first = self.create()
        again = self.create()
        self.assertEqual(first['id'], again['id'])
        self.assertEqual(first['deadline'], again['deadline'])
        self.assertEqual(again['tool_calls'], 0)
        with self.assertRaisesRegex(Work4ceError, 'idempotency_conflict'):
            self.store.create_workflow(TENANT, SUBJECT, 'different-query', 20, 'request-one')
        with self.assertRaisesRegex(Work4ceError, 'idempotency_conflict'):
            self.create(max_tool_calls=1)
        with self.assertRaisesRegex(Work4ceError, 'idempotency_conflict'):
            self.create(duration_seconds=99)
        other = self.store.create_workflow('different-tenant', SUBJECT, 'PowerShell', 20, 'request-one')
        self.assertNotEqual(other['id'], first['id'])
        for tenant, subject in [(TENANT, 'different-subject'), ('different-tenant', SUBJECT)]:
            with self.assertRaisesRegex(Work4ceError, 'workflow_not_found'):
                self.store.get_workflow(tenant, subject, first['id'])
            with self.assertRaisesRegex(Work4ceError, 'workflow_not_found'):
                self.store.cancel_workflow(tenant, subject, first['id'])
        with self.store.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(investigations.c.id)).all()), 2)
        self.assertEqual(len(self.store.audit_rows(TENANT)), 1)

    def test_oidc_subject_length_256_is_preserved(self):
        subject = 's' * 256
        row = self.store.create_workflow(TENANT, subject, 'PowerShell', 20, 'long-subject')
        self.assertEqual(self.store.get_workflow(TENANT, subject, row['id'])['subject'], subject)
        with self.assertRaisesRegex(Work4ceError, 'invalid_workflow_request'):
            self.store.create_workflow(TENANT, 's' * 257, 'PowerShell', 20, 'too-long')

    def test_budget_reservation_survives_restart(self):
        identity = self.create(max_tool_calls=1)['id']
        self.claim(identity)
        state = self.store.reserve_tool_call(TENANT, SUBJECT, identity, 'worker-one')
        self.assertEqual(state['tool_calls'], 1)
        self.store.release_workflow(TENANT, SUBJECT, identity, 'worker-one')
        self.store.close()
        self.store = Store(self.database)
        self.claim(identity, 'worker-two')
        with self.assertRaisesRegex(Work4ceError, 'workflow_budget_exhausted'):
            self.store.reserve_tool_call(TENANT, SUBJECT, identity, 'worker-two')
        self.assertEqual(self.store.get_workflow(TENANT, SUBJECT, identity)['tool_calls'], 1)

    def test_checkpoint_survives_restart_and_atomic_finish(self):
        identity = self.create()['id']
        self.claim(identity)
        self.store.reserve_tool_call(TENANT, SUBJECT, identity, 'worker-one')
        checkpoint = {'data': {'events': []}, 'connector_id': 'demo-rest', 'synthetic': True}
        self.store.checkpoint_workflow(TENANT, SUBJECT, identity, 'worker-one', checkpoint)
        self.store.release_workflow(TENANT, SUBJECT, identity, 'worker-one')
        self.store.close()
        self.store = Store(self.database)
        resumed = self.claim(identity, 'worker-two')
        self.assertEqual(resumed['state'], 'collected')
        self.assertEqual(resumed['checkpoint'], checkpoint)
        self.assertEqual(resumed['tool_calls'], 1)
        with patch.object(self.store, '_audit', side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.store.finish_workflow(TENANT, SUBJECT, identity, 'worker-two', {'synthetic': True}, 'completed')
        self.assertEqual(self.store.get_workflow(TENANT, SUBJECT, identity)['state'], 'collected')
        self.assertEqual(self.store.get(TENANT, identity)['status'], 'running')
        self.store.finish_workflow(TENANT, SUBJECT, identity, 'worker-two', {'synthetic': True}, 'completed')
        terminal = self.store.get_workflow(TENANT, SUBJECT, identity)
        self.assertEqual(terminal['state'], 'completed')
        self.assertIsNone(terminal['lease_owner'])
        self.assertEqual(self.store.get(TENANT, identity)['report'], {'synthetic': True})
        self.assertEqual(self.store.cancel_workflow(TENANT, SUBJECT, identity)['state'], 'completed')
        with self.assertRaisesRegex(Work4ceError, 'workflow_terminal'):
            self.claim(identity, 'worker-three')

    def test_cancel_invalidates_lease_and_preserves_checkpoint(self):
        identity = self.create()['id']
        self.claim(identity)
        self.store.reserve_tool_call(TENANT, SUBJECT, identity, 'worker-one')
        checkpoint = {'data': {'events': []}}
        self.store.checkpoint_workflow(TENANT, SUBJECT, identity, 'worker-one', checkpoint)
        state = self.store.cancel_workflow(TENANT, SUBJECT, identity)
        self.assertEqual(state['state'], 'cancelled')
        self.assertEqual(state['checkpoint'], checkpoint)
        self.assertIsNone(state['lease_owner'])
        with self.assertRaisesRegex(Work4ceError, 'workflow_terminal'):
            self.store.finish_workflow(TENANT, SUBJECT, identity, 'worker-one', {'synthetic': True}, 'completed')
        with self.assertRaisesRegex(Work4ceError, 'workflow_lease_required'):
            self.store.finish(TENANT, SUBJECT, identity, {'override': True}, 'completed')
        self.assertEqual(self.store.get(TENANT, identity)['status'], 'cancelled')
        self.assertEqual(self.store.get(TENANT, identity)['report']['error'], 'workflow_cancelled')

    def test_expired_lease_fences_old_worker_and_can_be_reclaimed(self):
        identity = self.create()['id']
        self.claim(identity)
        with self.assertRaisesRegex(Work4ceError, 'workflow_busy'):
            self.claim(identity, 'worker-two')
        with self.store.engine.begin() as connection:
            connection.execute(update(workflow_state).where(workflow_state.c.id == identity).values(lease_until=time.time()-1))
        with self.assertRaisesRegex(Work4ceError, 'workflow_lease_lost'):
            self.store.reserve_tool_call(TENANT, SUBJECT, identity, 'worker-one')
        self.claim(identity, 'worker-two')
        with self.assertRaisesRegex(Work4ceError, 'workflow_lease_lost'):
            self.store.finish_workflow(TENANT, SUBJECT, identity, 'worker-one', {}, 'failed')
        self.store.release_workflow(TENANT, SUBJECT, identity, 'worker-one')
        self.assertEqual(self.store.get_workflow(TENANT, SUBJECT, identity)['lease_owner'], 'worker-two')

    def test_deadline_expiry_finalizes_and_fences_work(self):
        identity = self.create()['id']
        self.claim(identity)
        with self.store.engine.begin() as connection:
            connection.execute(update(workflow_state).where(workflow_state.c.id == identity).values(deadline=time.time()-1))
        with self.assertRaisesRegex(Work4ceError, 'workflow_deadline_exceeded'):
            self.store.reserve_tool_call(TENANT, SUBJECT, identity, 'worker-one')
        with self.assertRaisesRegex(Work4ceError, 'workflow_deadline_exceeded'):
            self.claim(identity, 'worker-two')
        self.assertEqual(self.store.get_workflow(TENANT, SUBJECT, identity)['state'], 'failed')
        self.assertEqual(self.store.get(TENANT, identity)['report']['error'], 'workflow_deadline_exceeded')
        with self.assertRaisesRegex(Work4ceError, 'workflow_terminal'):
            self.store.finish_workflow(TENANT, SUBJECT, identity, 'worker-one', {}, 'completed')

    def test_checkpoint_hash_and_size_rejected(self):
        identity = self.create()['id']
        self.claim(identity)
        self.store.reserve_tool_call(TENANT, SUBJECT, identity, 'worker-one')
        with self.assertRaisesRegex(Work4ceError, 'invalid_workflow_checkpoint'):
            self.store.checkpoint_workflow(TENANT, SUBJECT, identity, 'worker-one', {'blob':'x'*262144})
        self.store.checkpoint_workflow(TENANT, SUBJECT, identity, 'worker-one', {'events':[]})
        with self.store.engine.begin() as connection:
            connection.execute(update(workflow_state).where(workflow_state.c.id == identity).values(checkpoint='{}'))
        with self.assertRaisesRegex(Work4ceError, 'checkpoint_integrity_failure'):
            self.store.get_workflow(TENANT, SUBJECT, identity)

    def test_invalid_requests_do_not_create_rows(self):
        for changes in ({'max_tool_calls':0}, {'max_tool_calls':True}, {'duration_seconds':float('inf')},
                        {'duration_seconds':0}, {'duration_seconds':True}):
            with self.subTest(changes=changes), self.assertRaisesRegex(Work4ceError, 'invalid_workflow_request'):
                self.create(**changes)
        with self.assertRaisesRegex(Work4ceError, 'invalid_workflow_request'):
            self.store.create_workflow(TENANT, SUBJECT, 'PowerShell', True, 'invalid')
        with self.store.engine.connect() as connection:
            self.assertEqual(connection.execute(select(workflow_state)).all(), [])
            self.assertEqual(connection.execute(select(investigations)).all(), [])

    def test_pending_quota_replay_scope_and_cancel_releases_slot(self):
        rows = [self.create(key='quota-' + str(index)) for index in range(100)]
        with self.assertRaisesRegex(Work4ceError, 'workflow_queue_full') as caught:
            self.create(key='overflow')
        self.assertEqual(caught.exception.status, 429)
        # Replay must succeed at capacity without adding an audit or parent row.
        self.assertEqual(self.create(key='quota-0')['id'], rows[0]['id'])
        with self.assertRaisesRegex(Work4ceError, 'idempotency_conflict'):
            self.store.create_workflow(TENANT, SUBJECT, 'different', 20, 'quota-0')
        self.store.create_workflow('another-tenant', SUBJECT, 'PowerShell', 20, 'quota-0')
        self.store.create_workflow(TENANT, 'another-subject', 'PowerShell', 20, 'quota-0')
        self.store.cancel_workflow(TENANT, SUBJECT, rows[0]['id'])
        self.assertEqual(self.create(key='replacement')['state'], 'queued')
        with self.assertRaisesRegex(Work4ceError, 'workflow_queue_full'):
            self.create(key='still-full')
        with self.store.engine.connect() as connection:
            ids = connection.execute(select(investigations.c.id).where(
                investigations.c.tenant == TENANT, investigations.c.subject == SUBJECT)).all()
            self.assertEqual(len(ids), 101)
        self.assertEqual(sum(action == 'workflow.create' for action, _, _ in self.store.audit_rows(TENANT)), 102)

    def test_simultaneous_last_queue_slot_accepts_only_one_request(self):
        for index in range(99):
            self.create(key='existing-' + str(index))
        clients = [Store(self.database), Store(self.database)]
        barrier = threading.Barrier(2)
        def create(client, key):
            barrier.wait(timeout=5)
            try:
                client.create_workflow(TENANT, SUBJECT, 'PowerShell', 20, key)
                return 'accepted'
            except Work4ceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(create, client, 'last-' + str(index)) for index, client in enumerate(clients)]
                results = [future.result(timeout=15) for future in futures]
            self.assertCountEqual(results, ['accepted', 'workflow_queue_full'])
            with self.store.engine.connect() as connection:
                self.assertEqual(len(connection.execute(select(workflow_state.c.id)).all()), 100)
                self.assertEqual(len(connection.execute(select(investigations.c.id)).all()), 100)
            self.assertEqual(len(self.store.audit_rows(TENANT)), 100)
        finally:
            for client in clients:
                client.close()

    def test_simultaneous_idempotency_has_one_parent_and_one_audit(self):
        clients = [Store(self.database), Store(self.database)]
        barrier = threading.Barrier(2)
        def create(client):
            barrier.wait(timeout=5)
            return client.create_workflow(TENANT, SUBJECT, 'PowerShell', 20, 'race-key')['id']
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(create, client) for client in clients]
                identities = [future.result(timeout=15) for future in futures]
            self.assertEqual(identities[0], identities[1])
            with self.store.engine.connect() as connection:
                self.assertEqual(len(connection.execute(select(investigations.c.id)).all()), 1)
                self.assertEqual(len(connection.execute(select(workflow_state.c.id)).all()), 1)
            self.assertEqual(len(self.store.audit_rows(TENANT)), 1)
        finally:
            for client in clients:
                client.close()

    def test_simultaneous_claim_has_one_lease_owner(self):
        identity = self.create()['id']
        clients = [Store(self.database), Store(self.database)]
        barrier = threading.Barrier(2)
        def claim(client, worker):
            barrier.wait(timeout=5)
            try:
                return client.claim_workflow(TENANT, SUBJECT, identity, worker)['lease_owner']
            except Work4ceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(claim, client, 'worker-'+str(i)) for i, client in enumerate(clients)]
                results = [future.result(timeout=15) for future in futures]
            self.assertEqual(results.count('workflow_busy'), 1)
            owner = self.store.get_workflow(TENANT, SUBJECT, identity)['lease_owner']
            self.assertIn(owner, results)
        finally:
            for client in clients:
                client.close()


class SQLiteWorkflowTests(WorkflowContract, unittest.TestCase):
    def setUp(self):
        test_storage.SQLiteStoreTests.setUp(self)

    def tearDown(self):
        test_storage.SQLiteStoreTests.tearDown(self)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'), 'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL workflow storage unrun')
class PostgreSQLWorkflowTests(WorkflowContract, unittest.TestCase):
    def setUp(self):
        test_storage.PostgreSQLStoreTests.setUp(self)

    def tearDown(self):
        test_storage.PostgreSQLStoreTests.tearDown(self)


class WorkflowMigrationTests(unittest.TestCase):
    def test_upgrade_version_one_keeps_reports_and_adds_workflows(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory)/'version-one.db')
            engine = create_engine('sqlite:///' + database)
            with engine.begin() as connection:
                command.upgrade(_config(connection), '0001_foundation')
                connection.execute(investigations.insert().values(id='retained',tenant=TENANT,subject=SUBJECT,
                    status='completed',report='{}',report_hash=__import__('hashlib').sha256(b'{}').hexdigest(),created_at='past',updated_at='past'))
                connection.execute(audit_table.insert().values(tenant=TENANT,subject=SUBJECT,action='legacy',target='retained',outcome='ok',timestamp='past'))
            engine.dispose()
            migrate(database)
            migrate(database)
            store = Store(database)
            self.addCleanup(store.close)
            self.assertEqual(store.get(TENANT,'retained')['report'], {})
            self.assertEqual(store.audit_rows(TENANT), [('legacy','retained','ok')])
            self.assertEqual(store.create_workflow(TENANT,SUBJECT,'PowerShell',20,'new')['state'], 'queued')
            with store.engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one(), HEAD)
