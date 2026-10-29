"""Model reservations remain charged across crashes, failure, and runtime restart."""
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
from work4ce_assistant.contracts import Work4ceError, digest
from work4ce_assistant.storage import HEAD, Store, _config, model_attempts, migrate, workflow_state

TENANT, SUBJECT, WORKER = 'model-tenant', 'model-analyst', 'model-worker'
INPUT, CONFIG = 'a' * 64, 'b' * 64


def result(value=True, input_tokens=10, output_tokens=20):
    return {'output': {'ok': value}, 'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'provider': 'fixture', 'model': 'synthetic'}


class ModelContract:
    def create(self, key='model-request', **kwargs):
        identity = self.store.create_workflow(TENANT, SUBJECT, 'PowerShell', 20, key, **kwargs)['id']
        self.store.claim_workflow(TENANT, SUBJECT, identity, WORKER)
        return identity

    def reserve(self, identity, **kwargs):
        values = dict(reserved_tokens=50, reserved_cost_microusd=10,
                      max_calls=2, max_tokens=100, max_cost_microusd=20)
        values.update(kwargs)
        return self.store.reserve_model_call(TENANT, SUBJECT, identity, WORKER, 'plan', INPUT, CONFIG, **values)

    def complete(self, identity, attempt, output=None, **kwargs):
        values = dict(actual_input_tokens=10, actual_output_tokens=20, actual_cost_microusd=5)
        values.update(kwargs)
        self.store.complete_model_call(TENANT, SUBJECT, identity, WORKER, attempt,
                                      result() if output is None else output, **values)

    def test_cache_and_actual_usage_survive_restart(self):
        identity = self.create()
        self.assertIsNone(self.store.get_model_result(TENANT, SUBJECT, identity, 'plan', INPUT, CONFIG))
        self.assertIsNone(self.store.model_usage(TENANT, SUBJECT, identity)['max_model_calls'])
        attempt = self.reserve(identity)
        self.complete(identity, attempt)
        self.store.close()
        self.store = Store(self.database)
        self.assertEqual(self.store.get_model_result(TENANT, SUBJECT, identity, 'plan', INPUT, CONFIG), result())
        self.assertIsNone(self.store.get_model_result(TENANT, SUBJECT, identity, 'assessment', INPUT, CONFIG))
        usage = self.store.model_usage(TENANT, SUBJECT, identity)
        self.assertEqual(usage, {'calls':1, 'reserved_tokens':50, 'reserved_cost_microusd':10,
            'actual_input_tokens':10, 'actual_output_tokens':20, 'actual_cost_microusd':5,
            'max_model_calls':2, 'max_model_tokens':100, 'max_model_cost_microusd':20})
        with self.assertRaisesRegex(Work4ceError, 'model_attempt_terminal'):
            self.complete(identity, attempt)

    def test_failed_and_crashed_attempts_are_never_refunded(self):
        identity = self.create()
        failed = self.reserve(identity)
        self.store.fail_model_call(TENANT, SUBJECT, identity, WORKER, failed, 'provider_unavailable')
        reserved = self.reserve(identity)
        self.store.release_workflow(TENANT, SUBJECT, identity, WORKER)
        self.store.close()
        self.store = Store(self.database)
        self.store.claim_workflow(TENANT, SUBJECT, identity, WORKER)
        with self.assertRaisesRegex(Work4ceError, 'model_budget_exhausted'):
            self.reserve(identity)
        usage = self.store.model_usage(TENANT, SUBJECT, identity)
        self.assertEqual(usage['calls'], 2)
        self.assertEqual(usage['reserved_tokens'], 100)
        self.assertEqual(usage['reserved_cost_microusd'], 20)
        self.assertEqual(usage['actual_input_tokens'], 0)
        self.assertIsNone(self.store.get_model_result(TENANT, SUBJECT, identity, 'plan', INPUT, CONFIG))
        with self.assertRaisesRegex(Work4ceError, 'model_attempt_terminal'):
            self.complete(identity, failed)
        self.assertIsInstance(reserved, str)

    def test_limits_and_route_config_cannot_be_reset(self):
        identity = self.create()
        self.reserve(identity)
        for changes in ({'max_calls':3}, {'max_tokens':101}, {'max_cost_microusd':21}):
            with self.subTest(changes=changes), self.assertRaisesRegex(Work4ceError, 'model_configuration_changed'):
                self.reserve(identity, **changes)
        with self.assertRaisesRegex(Work4ceError, 'model_configuration_changed'):
            self.store.reserve_model_call(TENANT, SUBJECT, identity, WORKER, 'assessment', INPUT, 'c'*64,
                reserved_tokens=50,reserved_cost_microusd=10,max_calls=2,max_tokens=100,max_cost_microusd=20)
        self.assertEqual(self.store.model_usage(TENANT, SUBJECT, identity)['calls'], 1)

    def test_each_budget_is_enforced_and_invalid_budgets_do_not_charge(self):
        for index, limits in enumerate(({'max_calls':1}, {'max_tokens':50}, {'max_cost_microusd':10})):
            identity = self.create(key='limit-'+str(index))
            self.reserve(identity, **limits)
            with self.subTest(limits=limits), self.assertRaisesRegex(Work4ceError, 'model_budget_exhausted'):
                self.reserve(identity, **limits)
        identity = self.create(key='invalid-budgets')
        for invalid in ({'reserved_tokens':0}, {'reserved_tokens':True}, {'max_calls':9},
                        {'max_tokens':262145}, {'reserved_cost_microusd':-1}, {'max_cost_microusd':True}):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(Work4ceError, 'invalid_model_budget'):
                self.reserve(identity, **invalid)
        self.assertEqual(self.store.model_usage(TENANT, SUBJECT, identity)['calls'], 0)

    def test_invalid_usage_output_and_error_codes_fail_closed(self):
        identity = self.create()
        attempt = self.reserve(identity)
        for invalid in ({'actual_input_tokens':-1}, {'actual_output_tokens':True},
                        {'actual_cost_microusd':11}, {'actual_input_tokens':31}):
            with self.subTest(invalid=invalid), self.assertRaises(Work4ceError):
                self.complete(identity, attempt, **invalid)
        with self.assertRaisesRegex(Work4ceError, 'model_reservation_exceeded'):
            self.complete(identity, attempt, result(input_tokens=40,output_tokens=20),actual_input_tokens=40)
        for invalid_result in ({'output':{}}, result(value='x'*65536), {**result(), 'unreviewed':'extra'}):
            with self.assertRaisesRegex(Work4ceError, 'invalid_model_result'):
                self.complete(identity, attempt, invalid_result)
        with self.assertRaisesRegex(Work4ceError, 'invalid_model_error_code'):
            self.store.fail_model_call(TENANT,SUBJECT,identity,WORKER,attempt,'secret=unsafe token')
        self.assertEqual(self.store.model_usage(TENANT,SUBJECT,identity)['actual_input_tokens'], 0)
        self.complete(identity, attempt)

    def test_isolation_cancellation_and_deadline_fences(self):
        identity = self.create()
        attempt = self.reserve(identity)
        for tenant, subject in [('other-tenant',SUBJECT), (TENANT,'other-subject')]:
            with self.assertRaisesRegex(Work4ceError, 'workflow_not_found'):
                self.store.model_usage(tenant,subject,identity)
            with self.assertRaisesRegex(Work4ceError, 'workflow_not_found'):
                self.store.get_model_result(tenant,subject,identity,'plan',INPUT,CONFIG)
            with self.assertRaisesRegex(Work4ceError, 'workflow_not_found'):
                self.store.complete_model_call(tenant,subject,identity,WORKER,attempt,result(),
                    actual_input_tokens=10,actual_output_tokens=20,actual_cost_microusd=5)
        self.store.cancel_workflow(TENANT,SUBJECT,identity)
        with self.assertRaisesRegex(Work4ceError, 'workflow_terminal'):
            self.complete(identity,attempt)
        with self.assertRaisesRegex(Work4ceError, 'workflow_terminal'):
            self.store.fail_model_call(TENANT,SUBJECT,identity,WORKER,attempt,'provider_failed')
        other = self.create(key='deadline')
        pending = self.reserve(other)
        with self.store.engine.begin() as connection:
            connection.execute(update(workflow_state).where(workflow_state.c.id == other).values(deadline=time.time()-1))
        with self.assertRaisesRegex(Work4ceError, 'workflow_deadline_exceeded'):
            self.complete(other,pending)
        self.assertEqual(self.store.model_usage(TENANT,SUBJECT,other)['calls'],1)

    def test_latest_completion_and_cache_integrity(self):
        identity = self.create()
        first, second = self.reserve(identity), self.reserve(identity)
        self.complete(identity,second,result(value='second'))
        self.complete(identity,first,result(value='first-finished-last'))
        self.assertEqual(self.store.get_model_result(TENANT,SUBJECT,identity,'plan',INPUT,CONFIG)['output'], {'ok':'first-finished-last'})
        with self.store.engine.begin() as connection:
            connection.execute(update(model_attempts).where(model_attempts.c.id == first).values(result='{}'))
        with self.assertRaisesRegex(Work4ceError,'model_result_integrity_failure'):
            self.store.get_model_result(TENANT,SUBJECT,identity,'plan',INPUT,CONFIG)

    def test_model_writes_and_audit_are_atomic(self):
        identity = self.create()
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.reserve(identity)
        self.assertEqual(self.store.model_usage(TENANT,SUBJECT,identity)['calls'],0)
        self.assertIsNone(self.store.get_workflow(TENANT,SUBJECT,identity)['model_limits_hash'])
        attempt = self.reserve(identity)
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled audit failure')):
            with self.assertRaises(RuntimeError):
                self.complete(identity,attempt)
        self.assertIsNone(self.store.get_model_result(TENANT,SUBJECT,identity,'plan',INPUT,CONFIG))
        self.assertEqual(self.store.model_usage(TENANT,SUBJECT,identity)['calls'],1)
        self.complete(identity,attempt)

    def test_simultaneous_last_reservation_cannot_exceed_budget(self):
        identity = self.create()
        clients = [Store(self.database),Store(self.database)]
        barrier = threading.Barrier(2)
        def reserve(client):
            barrier.wait(timeout=5)
            try:
                client.reserve_model_call(TENANT,SUBJECT,identity,WORKER,'plan',INPUT,CONFIG,
                    reserved_tokens=50,reserved_cost_microusd=10,max_calls=1,max_tokens=50,max_cost_microusd=10)
                return 'reserved'
            except Work4ceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = [future.result(timeout=15) for future in [executor.submit(reserve,client) for client in clients]]
            self.assertEqual(outcomes.count('reserved'),1)
            self.assertTrue(set(outcomes) <= {'reserved','model_budget_exhausted','workflow_lease_lost'})
            self.assertEqual(self.store.model_usage(TENANT,SUBJECT,identity)['calls'],1)
            self.assertEqual(self.store.model_usage(TENANT,SUBJECT,identity)['reserved_tokens'],50)
        finally:
            for client in clients:
                client.close()

    def test_reasoning_configuration_is_bound_at_enqueue(self):
        row = self.store.create_workflow(TENANT,SUBJECT,'PowerShell',20,'bound',reasoning_config_hash=CONFIG)
        self.assertEqual(row['reasoning_config_hash'],CONFIG)
        self.assertEqual(self.store.create_workflow(TENANT,SUBJECT,'PowerShell',20,'bound',reasoning_config_hash=CONFIG)['id'],row['id'])
        for changed in (None, 'c'*64):
            with self.assertRaisesRegex(Work4ceError,'idempotency_conflict'):
                self.store.create_workflow(TENANT,SUBJECT,'PowerShell',20,'bound',reasoning_config_hash=changed)
        with self.assertRaisesRegex(Work4ceError,'invalid_workflow_request'):
            self.store.create_workflow(TENANT,SUBJECT,'PowerShell',20,'invalid',reasoning_config_hash='not-a-hash')
        deterministic = self.store.create_workflow(TENANT,SUBJECT,'PowerShell',20,'deterministic')
        self.assertEqual(deterministic['request_hash'], digest({'query':'PowerShell','limit':20,'max_tool_calls':2,'duration_seconds':120.0}))


class SQLiteModelTests(ModelContract, unittest.TestCase):
    def setUp(self):
        test_storage.SQLiteStoreTests.setUp(self)

    def tearDown(self):
        test_storage.SQLiteStoreTests.tearDown(self)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'), 'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL model storage unrun')
class PostgreSQLModelTests(ModelContract, unittest.TestCase):
    def setUp(self):
        test_storage.PostgreSQLStoreTests.setUp(self)

    def tearDown(self):
        test_storage.PostgreSQLStoreTests.tearDown(self)


class ModelMigrationTests(unittest.TestCase):
    def test_v2_workflow_state_is_preserved_without_rewriting_request_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory)/'version-two.db')
            engine = create_engine('sqlite:///' + database)
            request_hash = digest({'query':'PowerShell','limit':20,'max_tool_calls':2,'duration_seconds':120.0})
            with engine.begin() as connection:
                command.upgrade(_config(connection),'0002_workflows')
                connection.execute(text("INSERT INTO investigations(id,tenant,subject,status,created_at,updated_at) VALUES ('v2',:tenant,:subject,'running','past','past')"), {'tenant':TENANT,'subject':SUBJECT})
                connection.execute(text('INSERT INTO workflow_state(id,tenant,subject,idempotency_key,request_hash,query,"limit",max_tool_calls,tool_calls,deadline,state,revision) VALUES (:id,:tenant,:subject,:key,:hash,:query,20,2,0,:deadline,:state,0)'),
                    {'id':'v2','tenant':TENANT,'subject':SUBJECT,'key':'v2-key','hash':request_hash,'query':'PowerShell','deadline':time.time()+120,'state':'queued'})
            engine.dispose()
            migrate(database)
            migrate(database)
            store = Store(database)
            self.addCleanup(store.close)
            row = store.get_workflow(TENANT,SUBJECT,'v2')
            self.assertEqual(row['request_hash'],request_hash)
            self.assertIsNone(row['reasoning_config_hash'])
            self.assertIsNone(row['model_limits_hash'])
            self.assertEqual(store.create_workflow(TENANT,SUBJECT,'PowerShell',20,'v2-key')['id'],'v2')
            with store.engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),HEAD)
