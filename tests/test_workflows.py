"""Durable workflow security/regression tests using tracked unit adapters.

Actual API, REST/MCP and database-process boundaries are exercised separately.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from sqlalchemy import select, update

from work4ce_assistant.api import CONNECTORS, PERMISSIONS, TENANT
from work4ce_assistant.contracts import CapabilityManifest, ConnectorManifest, ExecutionContext, Work4ceError
from work4ce_assistant.fixtures import SEARCH_CAPABILITY, search_events
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.investigation import Investigator
from work4ce_assistant.storage import Store, investigations


def context(**changes):
    return replace(ExecutionContext(TENANT, 'workflow-analyst', PERMISSIONS, CONNECTORS, True), **changes)


def manifest(identity='demo-rest', tenant=TENANT):
    return ConnectorManifest(connector_id=identity, name=identity, protocol='rest',
                             tenant_id=tenant, synthetic=True,
                             capability=CapabilityManifest(**SEARCH_CAPABILITY))


class TrackedAdapter:
    def __init__(self):
        self.calls = 0
        self.cancel_remaining = 0
        self.entered = asyncio.Event()
        self.release = None
        self.failure = None

    async def discover(self):
        return [deepcopy(SEARCH_CAPABILITY)]

    async def health(self):
        return True

    async def invoke(self, capability_id, arguments):
        self.calls += 1
        self.entered.set()
        if self.cancel_remaining:
            self.cancel_remaining -= 1
            raise asyncio.CancelledError
        if self.release is not None:
            await self.release.wait()
        if self.failure:
            raise self.failure
        return search_events(arguments)


class DurableWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = Store(':memory:')
        self.gateway = Gateway(self.store)
        self.adapter = TrackedAdapter()
        await self.gateway.register(manifest(), self.adapter, reviewed=True)
        self.agent = Investigator(self.gateway, self.store)

    async def asyncTearDown(self):
        self.store.close()

    def identity(self, store=None):
        with (store or self.store).engine.connect() as connection:
            return connection.execute(select(investigations.c.id)).scalar_one()

    async def checkpoint_interrupted(self, *, key='checkpoint-key'):
        # Simulate process interruption after durable evidence checkpoint, before
        # final report commit. Resume must reuse evidence rather than query again.
        with patch.object(self.store, 'finish_workflow', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await self.agent.investigate(context(), 'PowerShell', idempotency_key=key)
        identity = self.identity()
        self.assertEqual(self.adapter.calls, 1)
        self.assertNotEqual(self.store.get(TENANT, identity)['status'], 'completed')
        return identity

    async def test_idempotent_replay_has_stable_report_and_evidence_ids(self):
        first = await self.agent.investigate(context(), 'PowerShell', idempotency_key='stable-key')
        second = await self.agent.investigate(context(), 'PowerShell', idempotency_key='stable-key')
        self.assertEqual(first, second)
        self.assertTrue(first['report']['evidence'])
        self.assertEqual(self.adapter.calls, 1)
        replay = await Investigator(self.gateway, self.store).resume(context(), first['id'])
        self.assertEqual(replay, first)
        self.assertEqual(self.adapter.calls, 1)

    async def test_idempotency_key_binds_query_and_limit(self):
        first = await self.agent.investigate(context(), 'PowerShell', idempotency_key='bound-key')
        for arguments in (('different-query', 20), ('PowerShell', 1)):
            with self.subTest(arguments=arguments), self.assertRaises(Work4ceError) as raised:
                await self.agent.investigate(context(), *arguments, idempotency_key='bound-key')
            self.assertEqual(raised.exception.status, 409)
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(self.store.get(TENANT, first['id']), first)

    async def test_keys_are_isolated_by_tenant_and_subject(self):
        first = await self.agent.investigate(context(), 'PowerShell', idempotency_key='same-key')
        second = await self.agent.investigate(context(subject='another-analyst'), 'PowerShell', idempotency_key='same-key')
        other = TrackedAdapter()
        await self.gateway.register(manifest('demo-other', 'other-tenant'), other, reviewed=True)
        third = await self.agent.investigate(context(tenant_id='other-tenant', allowed_connectors=frozenset({'demo-other'})),
                                             'PowerShell', idempotency_key='same-key')
        self.assertEqual(len({first['id'], second['id'], third['id']}), 3)
        self.assertEqual(self.adapter.calls, 2)
        self.assertEqual(other.calls, 1)
        self.assertEqual(third['report']['tenant_id'], 'other-tenant')

    async def test_resume_checkpoint_does_not_query_again(self):
        identity = await self.checkpoint_interrupted()
        checkpoint = self.store.get_workflow(TENANT, context().subject, identity)['checkpoint']
        result = await self.agent.resume(context(), identity)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['report']['evidence'], checkpoint['evidence'])
        self.assertTrue(result['report']['evidence'])
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(await self.agent.resume(context(), identity), result)

    async def test_process_style_store_reopen_reuses_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'workflow.db')
            store = Store(path)
            adapter = TrackedAdapter()
            gateway = Gateway(store)
            await gateway.register(manifest(), adapter, reviewed=True)
            agent = Investigator(gateway, store)
            try:
                with patch.object(store, 'finish_workflow', side_effect=asyncio.CancelledError):
                    with self.assertRaises(asyncio.CancelledError):
                        await agent.investigate(context(), 'PowerShell', idempotency_key='restart-key')
                identity = self.identity(store)
            finally:
                store.close()
            resumed_store = Store(path)
            try:
                gateway = Gateway(resumed_store)
                await gateway.register(manifest(), adapter, reviewed=True)
                result = await Investigator(gateway, resumed_store).resume(context(), identity)
                self.assertEqual(result['status'], 'completed')
                self.assertEqual(adapter.calls, 1)
                self.assertTrue(result['report']['evidence'])
            finally:
                resumed_store.close()

    async def test_interrupted_call_consumes_persisted_budget_across_runtime_recreation(self):
        self.adapter.cancel_remaining = 2
        agent = Investigator(self.gateway, self.store, max_tool_calls=2)
        with self.assertRaises(asyncio.CancelledError):
            await agent.investigate(context(), 'PowerShell')
        identity = self.identity()
        self.assertEqual(self.adapter.calls, 1)
        with self.assertRaises(asyncio.CancelledError):
            await Investigator(self.gateway, self.store, max_tool_calls=2).resume(context(), identity)
        self.assertEqual(self.adapter.calls, 2)
        with self.assertRaises(Work4ceError):
            await Investigator(self.gateway, self.store, max_tool_calls=2).resume(context(), identity)
        self.assertEqual(self.adapter.calls, 2)
        self.assertEqual(self.store.get(TENANT, identity)['status'], 'failed')

    async def test_task_cancellation_releases_lease_and_remains_recoverable(self):
        self.adapter.release = asyncio.Event()
        task = asyncio.create_task(self.agent.investigate(context(), 'PowerShell'))
        await asyncio.wait_for(self.adapter.entered.wait(), timeout=2)
        identity = self.identity()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.adapter.release.set()
        result = await self.agent.resume(context(), identity)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.adapter.calls, 2)

    async def test_concurrent_resume_has_one_lease_owner_and_one_execution(self):
        self.adapter.cancel_remaining = 1
        with self.assertRaises(asyncio.CancelledError):
            await self.agent.investigate(context(), 'PowerShell')
        identity = self.identity()
        self.adapter.entered.clear()
        self.adapter.release = asyncio.Event()
        task = asyncio.create_task(self.agent.resume(context(), identity))
        await asyncio.wait_for(self.adapter.entered.wait(), timeout=2)
        try:
            with self.assertRaises(Work4ceError) as raised:
                await Investigator(self.gateway, self.store).resume(context(), identity)
            self.assertEqual(raised.exception.status, 409)
            self.assertEqual(self.adapter.calls, 2)
        finally:
            self.adapter.release.set()
            await task
        self.assertEqual(self.store.get(TENANT, identity)['status'], 'completed')

    async def test_explicit_cancel_fences_completion_of_inflight_call(self):
        self.adapter.release = asyncio.Event()
        task = asyncio.create_task(self.agent.investigate(context(), 'PowerShell'))
        await asyncio.wait_for(self.adapter.entered.wait(), timeout=2)
        identity = self.identity()
        try:
            await self.agent.cancel(context(), identity)
        finally:
            self.adapter.release.set()
        try:
            await task
        except Work4ceError:
            pass
        self.assertEqual(self.store.get(TENANT, identity)['status'], 'cancelled')
        with self.assertRaises(Work4ceError):
            await self.agent.resume(context(), identity)
        self.assertEqual(self.adapter.calls, 1)

    async def test_cross_subject_or_tenant_cannot_resume_or_cancel(self):
        identity = await self.checkpoint_interrupted()
        for foreign in (context(subject='other-subject'), context(tenant_id='other-tenant')):
            for operation in (self.agent.resume, self.agent.cancel):
                with self.subTest(context=foreign, operation=operation.__name__), self.assertRaises(Work4ceError) as raised:
                    await operation(foreign, identity)
                self.assertEqual(raised.exception.status, 404)
        result = await self.agent.resume(context(), identity)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.adapter.calls, 1)

    async def test_revoked_connector_cannot_authorize_checkpoint_reuse(self):
        identity = await self.checkpoint_interrupted()
        self.gateway.disable(context(permissions=PERMISSIONS | {'connectors:admin'}), 'demo-rest')
        with self.assertRaises(Work4ceError):
            await self.agent.resume(context(), identity)
        self.assertNotEqual(self.store.get(TENANT, identity)['status'], 'completed')
        self.assertEqual(self.adapter.calls, 1)

    async def test_removed_permissions_cannot_authorize_checkpoint_reuse(self):
        identity = await self.checkpoint_interrupted()
        with self.assertRaises(Work4ceError) as raised:
            await self.agent.resume(context(permissions=frozenset({'investigations:run'})), identity)
        self.assertEqual(raised.exception.status, 403)
        self.assertNotEqual(self.store.get(TENANT, identity)['status'], 'completed')
        self.assertEqual(self.adapter.calls, 1)

    async def test_failed_connector_persists_failure_and_audit_without_fabricated_evidence(self):
        self.adapter.failure = RuntimeError('private connector details')
        with self.assertRaises(Work4ceError):
            await self.agent.investigate(context(), 'PowerShell')
        identity = self.identity()
        result = self.store.get(TENANT, identity)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['report']['evidence'], [])
        self.assertIn(('capability.execute', 'demo-rest', 'failed'), self.store.audit_rows(TENANT))
        self.assertNotIn('private connector details', str(result))

    async def test_expired_durable_deadline_is_terminal_without_connector_call(self):
        from work4ce_assistant.storage import workflow_state
        row = self.store.create_workflow(TENANT, context().subject, 'PowerShell', 20,
                                         'expired-workflow', max_tool_calls=2, duration_seconds=120)
        identity = row['id']
        with self.store.engine.begin() as connection:
            connection.execute(update(workflow_state).where(workflow_state.c.id == identity)
                               .values(deadline=time.time() - 1))
        with self.assertRaises(Work4ceError):
            await self.agent.resume(context(), identity)
        result = self.store.get(TENANT, identity)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['report']['error'], 'workflow_deadline_exceeded')
        self.assertEqual(self.adapter.calls, 0)
        with self.assertRaises(Work4ceError):
            await self.agent.resume(context(), identity)
        self.assertEqual(self.adapter.calls, 0)

    async def test_completed_replay_rechecks_current_connector_grants(self):
        result = await self.agent.investigate(context(), 'PowerShell', idempotency_key='replay-revoked')
        self.gateway.disable(context(permissions=PERMISSIONS | {'connectors:admin'}), 'demo-rest')
        with self.assertRaises(Work4ceError) as raised:
            await self.agent.investigate(context(), 'PowerShell', idempotency_key='replay-revoked')
        self.assertEqual(raised.exception.status, 403)
        self.assertEqual(self.adapter.calls, 1)
        # Denial must not overwrite the already committed report.
        self.assertEqual(self.store.get(TENANT, result['id']), result)

    async def test_failure_after_checkpoint_preserves_checkpoint_and_audit(self):
        identity = await self.checkpoint_interrupted()
        checkpoint = self.store.get_workflow(TENANT, context().subject, identity)['checkpoint']
        self.assertIsNotNone(checkpoint)
        audit_before = self.store.audit_rows(TENANT)
        with patch.object(self.store, 'finish_workflow', side_effect=RuntimeError('private commit detail')):
            with self.assertRaises(Work4ceError):
                await self.agent.resume(context(), identity)
        self.assertEqual(self.store.get_workflow(TENANT, context().subject, identity)['checkpoint'], checkpoint)
        self.assertEqual(self.adapter.calls, 1)
        audit_after = self.store.audit_rows(TENANT)
        self.assertEqual(audit_after[:len(audit_before)], audit_before)
        self.assertIn(('workflow.checkpoint', identity, 'collected'), audit_after)

    async def test_actual_failover_invocation_consumes_durable_budget(self):
        other = TrackedAdapter()
        await self.gateway.register(manifest('demo-mcp'), other, reviewed=True)
        self.adapter.failure = RuntimeError('first connector unavailable')
        with self.assertRaises(Work4ceError) as raised:
            await Investigator(self.gateway, self.store, max_tool_calls=1).investigate(context(), 'PowerShell')
        self.assertEqual(raised.exception.code, 'workflow_budget_exhausted')
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(other.calls, 0)
        identity = self.identity()
        state = self.store.get_workflow(TENANT, context().subject, identity)
        self.assertEqual(state['tool_calls'], 1)
        self.assertEqual(state['state'], 'failed')

    async def test_generic_cleanup_failure_is_redacted_after_successful_commit(self):
        with patch.object(self.store, 'release_workflow', side_effect=RuntimeError('private cleanup detail')):
            with self.assertRaises(Work4ceError) as raised:
                await self.agent.investigate(context(), 'PowerShell')
        self.assertEqual(raised.exception.status, 503)
        self.assertEqual(raised.exception.code, 'workflow_persistence_failed')
        self.assertNotIn('private cleanup detail', str(raised.exception))
        identity = self.identity()
        saved = self.store.get(TENANT, identity)
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(await self.agent.resume(context(), identity), saved)
        self.assertEqual(self.adapter.calls, 1)

    async def test_cleanup_failure_preserves_task_cancellation_and_recoverable_lease(self):
        self.adapter.cancel_remaining = 1
        with patch.object(self.store, 'release_workflow', side_effect=RuntimeError('private cleanup detail')) as cleanup:
            with self.assertRaises(asyncio.CancelledError):
                await self.agent.investigate(context(), 'PowerShell')
        self.assertEqual(cleanup.call_count, 1)
        identity = self.identity()
        state = self.store.get_workflow(TENANT, context().subject, identity)
        self.assertNotIn(state['state'], {'completed', 'failed', 'cancelled'})
        self.assertIsNotNone(state['lease_owner'])
        self.store.release_workflow(TENANT, context().subject, identity, state['lease_owner'])
        result = await self.agent.resume(context(), identity)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.adapter.calls, 2)
