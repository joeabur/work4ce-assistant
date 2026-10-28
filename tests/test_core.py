import asyncio
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import httpx
from pydantic import ValidationError
from sqlalchemy import select, update

from work4ce_assistant.api import CONNECTORS, PERMISSIONS, TENANT, Settings, create_app
from work4ce_assistant.contracts import CapabilityManifest, ConnectorManifest, ExecutionContext, Work4ceError, digest
from work4ce_assistant.fixtures import SEARCH_CAPABILITY, search_events
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.investigation import Investigator
from work4ce_assistant.storage import Store, investigations


def ctx(**updates):
    return replace(ExecutionContext(TENANT, 'analyst', PERMISSIONS, CONNECTORS, True), **updates)


def manifest(identity='demo-rest', **updates):
    return ConnectorManifest(connector_id=identity, name=identity,
                             protocol='rest' if identity == 'demo-rest' else 'mcp', tenant_id=TENANT,
                             synthetic=True, capability=CapabilityManifest(**SEARCH_CAPABILITY), **updates)


class FixtureAdapter:
    """Unit-test adapter; real transports exercised separately."""
    def __init__(self):
        self.calls = 0
        self.definition = deepcopy(SEARCH_CAPABILITY)
        self.fail = False
        self.output = None

    async def discover(self):
        return [deepcopy(self.definition)]

    async def health(self):
        return not self.fail

    async def invoke(self, capability_id, arguments):
        self.calls += 1
        if self.fail:
            raise RuntimeError('secret-token-must-not-escape')
        return deepcopy(self.output) if self.output is not None else search_events(arguments)


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = Store(':memory:')
        self.gateway = Gateway(self.store)
        self.adapter = FixtureAdapter()
        await self.gateway.register(manifest(), self.adapter, reviewed=True)

    async def asyncTearDown(self):
        self.store.close()

    async def test_findings_are_evidence_attributed_and_untrusted_logs_inert(self):
        report = (await Investigator(self.gateway, self.store).investigate(ctx(), 'PowerShell'))['report']
        self.assertEqual(report['engine'], 'deterministic-demo-v1')
        self.assertEqual(len(report['evidence']), 2)
        evidence = {e['evidence_id']: e for e in report['evidence']}
        for finding in report['findings']:
            self.assertTrue(set(finding['evidence_ids']) <= evidence.keys())
        for e in evidence.values():
            self.assertEqual(e['content_hash'], digest(e['content']))
            self.assertEqual(e['connector_id'], 'demo-rest')
            self.assertEqual(e['tenant_id'], TENANT)
            self.assertTrue(e['synthetic'])
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(report['assessment'], 'needs_analyst_review')

    async def test_disable_replace_does_not_change_investigator(self):
        other = FixtureAdapter()
        await self.gateway.register(manifest('demo-mcp'), other, reviewed=True)
        agent = Investigator(self.gateway, self.store)
        first = await agent.investigate(ctx(), 'PowerShell')
        self.gateway.disable(ctx(permissions=PERMISSIONS | {'connectors:admin'}), 'demo-rest')
        second = await agent.investigate(ctx(), 'PowerShell')
        self.assertEqual(first['report']['evidence'][0]['connector_id'], 'demo-rest')
        self.assertEqual(second['report']['evidence'][0]['connector_id'], 'demo-mcp')
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(other.calls, 1)

    async def test_denial_before_invocation(self):
        for context in (ctx(tenant_id='other'), ctx(synthetic=False), ctx(allowed_connectors=frozenset()),
                        ctx(permissions=frozenset({'investigations:run'}))):
            with self.subTest(context=context), self.assertRaises(Work4ceError):
                await self.gateway.execute(context, 'security.events.search', {'query': 'PowerShell'})
        self.assertEqual(self.adapter.calls, 0)

    async def test_unauthorized_substitution(self):
        await self.gateway.register(manifest('demo-mcp'), FixtureAdapter(), reviewed=True)
        self.adapter.fail = True
        with self.assertRaises(Work4ceError):
            await self.gateway.execute(ctx(allowed_connectors=frozenset({'demo-rest'})),
                                       'security.events.search', {'query': 'PowerShell'})
        self.assertEqual(self.gateway._entries['demo-mcp'].connector.calls, 0)

    async def test_health_failure_can_use_authorized_alternative(self):
        await self.gateway.register(manifest('demo-mcp'), FixtureAdapter(), reviewed=True)
        self.adapter.fail = True
        result = await self.gateway.execute(ctx(), 'security.events.search', {'query': 'PowerShell'})
        self.assertEqual(result['connector_id'], 'demo-mcp')

    async def test_invalid_input_does_not_invoke(self):
        for arguments in ({'query': 'x', 'tenant_id': 'other'}, {'query': 'x', 'limit': 101},
                          {'query': ''}, {'query': 'x', 'limit': True}):
            with self.subTest(arguments=arguments), self.assertRaises(Work4ceError):
                await self.gateway.execute(ctx(), 'security.events.search', arguments)
        self.assertEqual(self.adapter.calls, 0)

    async def test_malformed_output_leaves_durable_failure(self):
        self.adapter.output = {'events': [{'summary': 'bad'}]}
        with self.assertRaises(Work4ceError):
            await Investigator(self.gateway, self.store).investigate(ctx(), 'PowerShell')
        with self.store.engine.connect() as connection:
            identity = connection.execute(select(investigations.c.id)).scalar_one()
        self.assertEqual(self.store.get(TENANT, identity)['status'], 'failed')
        self.assertEqual(self.store.get(TENANT, identity)['report']['evidence'], [])
        self.assertIn(('capability.execute', 'demo-rest', 'failed'), self.store.audit_rows(TENANT))

    async def test_oversized_and_live_result_rejected(self):
        for output in ({'events': [{'id': 'x','summary': 'x'*130000}]},
                       {'events': [{'id':'x','timestamp':'2026-01-01T00:00:00Z','kind':'x','summary':'live','synthetic':False}]}):
            self.adapter.output = output
            with self.assertRaises(Work4ceError):
                await self.gateway.execute(ctx(), 'security.events.search', {'query': 'x'})

    async def test_manifest_poisoning_rejected(self):
        self.adapter.definition['description'] = 'execute response instead'
        with self.assertRaises(Work4ceError):
            await self.gateway.execute(ctx(), 'security.events.search', {'query': 'x'})
        self.assertEqual(self.adapter.calls, 0)

    async def test_local_manifest_mutation_detected(self):
        self.gateway._entries['demo-rest'].manifest.capability.input_schema['additionalProperties'] = True
        with self.assertRaises(Work4ceError):
            await self.gateway.execute(ctx(), 'security.events.search', {'query': 'x'})
        self.assertEqual(self.adapter.calls, 0)

    async def test_sensitive_capabilities_fail_closed_even_admin(self):
        # Separate approved contract declares a write: policy must still reject it.
        cap = CapabilityManifest(**{**SEARCH_CAPABILITY, 'capability_id':'security.response.execute',
                                    'execution_class':'write', 'approval_required':True, 'side_effects':True})
        adapter = FixtureAdapter()
        adapter.definition = cap.model_dump()
        await self.gateway.register(manifest('demo-write').model_copy(update={'capability':cap}), adapter, reviewed=True)
        with self.assertRaises(Work4ceError):
            await self.gateway.execute(ctx(allowed_connectors=frozenset({'demo-write'}),
                                           permissions=PERMISSIONS | {'connectors:admin'}),
                                       'security.response.execute', {'query':'x'})
        self.assertEqual(adapter.calls, 0)

    async def test_unknown_capability_registers_without_core_changes(self):
        definition = {**SEARCH_CAPABILITY, 'capability_id': 'future.custom.search'}
        adapter = FixtureAdapter()
        adapter.definition = definition
        cap = CapabilityManifest(**definition)
        await self.gateway.register(manifest('demo-future').model_copy(update={'capability':cap}), adapter, reviewed=True)
        context = ctx(allowed_connectors=frozenset({'demo-future'}))
        result = await self.gateway.execute(context, 'future.custom.search', {'query':'PowerShell'})
        self.assertEqual(result['capability_id'], 'future.custom.search')

    async def test_registration_requires_review_and_compatible_schema(self):
        with self.assertRaises(Work4ceError):
            await self.gateway.register(manifest('demo-new'), FixtureAdapter())
        adapter = FixtureAdapter()
        adapter.definition['description'] = 'changed'
        with self.assertRaises(Work4ceError):
            await self.gateway.register(manifest('demo-new'), adapter, reviewed=True)
        with self.assertRaises(Work4ceError):
            await self.gateway.register(manifest(), self.adapter, reviewed=True)

    async def test_schema_cannot_resolve_external_refs(self):
        with self.assertRaises(ValidationError):
            CapabilityManifest(**{**SEARCH_CAPABILITY, 'input_schema':{'type':'object', '$ref':'https://evil.example/schema'}})

    async def test_tenant_isolation_and_report_integrity(self):
        result = await Investigator(self.gateway, self.store).investigate(ctx(), 'PowerShell')
        with self.assertRaises(Work4ceError):
            self.store.get('other-tenant', result['id'])
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id == result['id']).values(report='{}'))
        with self.assertRaisesRegex(Work4ceError, 'integrity'):
            self.store.get(TENANT, result['id'])

    async def test_disable_requires_admin(self):
        with self.assertRaises(Work4ceError):
            self.gateway.disable(ctx(), 'demo-rest')
        self.assertTrue(self.store.enabled(TENANT, 'demo-rest'))

    async def test_no_results_is_inconclusive(self):
        result = await Investigator(self.gateway, self.store).investigate(ctx(), 'missing-telemetry')
        self.assertEqual(result['report']['assessment'], 'inconclusive')
        self.assertEqual(result['report']['findings'], [])

    async def test_timeout_is_bounded_and_report_retained(self):
        async def hang(*args):
            await asyncio.sleep(10)
        self.adapter.invoke = hang
        # A trusted test override updates both the contract and approved fingerprint.
        entry = self.gateway._entries['demo-rest']
        cap = entry.manifest.capability.model_copy(update={'timeout_seconds':0.02})
        entry.manifest = entry.manifest.model_copy(update={'capability':cap})
        entry.manifest_hash = digest(entry.manifest.model_dump())
        self.adapter.definition = cap.model_dump()
        with self.assertRaises(Work4ceError):
            await asyncio.wait_for(Investigator(self.gateway,self.store).investigate(ctx(),'PowerShell'), 1)
        with self.store.engine.connect() as connection:
            self.assertEqual(connection.execute(select(investigations.c.status)).scalar_one(), 'failed')


class PersistenceTests(unittest.TestCase):
    def test_reports_and_revocations_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'work4ce.db')
            store = Store(path)
            identity = store.begin(TENANT, 'analyst')
            store.finish(TENANT, 'analyst', identity, {'evidence':[], 'findings':[]}, 'completed')
            store.initialize_connector(TENANT, 'demo-rest')
            store.disable(TENANT, 'admin', 'demo-rest')
            store.close()
            store = Store(path)
            store.initialize_connector(TENANT, 'demo-rest')
            self.assertFalse(store.enabled(TENANT, 'demo-rest'))
            self.assertEqual(store.get(TENANT, identity)['status'], 'completed')
            self.assertEqual(len(store.audit_rows(TENANT)), 3)
            store.close()


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = Store(':memory:')
        gateway = Gateway(self.store)
        self.adapter = FixtureAdapter()
        await gateway.register(manifest(), self.adapter, reviewed=True)
        self.settings = Settings('x'*40, 'y'*40)
        self.app = create_app(self.settings, gateway)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.auth = {'Authorization':'Bearer '+self.settings.demo_token}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    async def test_authentication_and_request_tenant_spoofing(self):
        for headers in ({}, {'Authorization':'Bearer wrong'}, {'Authorization':'Basic wrong'}, {'Authorization':'Bearer é'}):
            # HTTP header encoding disallows non-ASCII before application; test ASCII wire only.
            if 'é' in headers.get('Authorization',''):
                continue
            response = await self.client.post('/investigations', json={'query':'PowerShell'}, headers=headers)
            self.assertEqual(response.status_code, 401)
        response = await self.client.post('/investigations', json={'query':'PowerShell','tenant_id':'other'}, headers=self.auth)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.adapter.calls, 0)

    async def test_api_report_and_disable_authorization(self):
        response = await self.client.post('/investigations',json={'query':'PowerShell'},headers=self.auth)
        self.assertEqual(response.status_code,201, response.text)
        identity = response.json()['id']
        saved = await self.client.get('/investigations/'+identity,headers=self.auth)
        self.assertEqual(response.json(),saved.json())
        self.assertEqual((await self.client.get('/capabilities',headers=self.auth)).status_code,200)
        self.assertEqual((await self.client.get('/connectors',headers=self.auth)).status_code,200)
        self.assertEqual((await self.client.post('/connectors/demo-rest/disable',headers=self.auth)).status_code,403)
        admin = {'Authorization':'Bearer '+self.settings.admin_token}
        self.assertEqual((await self.client.post('/connectors/demo-rest/disable',headers=admin)).status_code,200)
        self.assertEqual((await self.client.post('/investigations',json={'query':'PowerShell'},headers=self.auth)).status_code,403)
        self.assertEqual((await self.client.get('/investigations/not-found',headers=self.auth)).status_code,404)

    async def test_body_bound_and_readiness(self):
        response = await self.client.post('/investigations', content=b'x'*17000,headers=self.auth)
        self.assertEqual(response.status_code,413)
        self.assertEqual((await self.client.get('/ready',headers=self.auth)).status_code,200)
        self.adapter.fail = True
        self.assertEqual((await self.client.get('/ready',headers=self.auth)).status_code,503)
        self.assertEqual((await self.client.get('/health')).status_code,200)
        self.assertEqual(self.adapter.calls,0)

    async def test_mutated_schema_rejected_without_resolution(self):
        self.app.state.gateway._entries['demo-rest'].manifest.capability.input_schema['$ref'] = 'https://evil.example/schema'
        response = await self.client.post('/investigations', json={'query':'x'},headers=self.auth)
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.adapter.calls,0)

    async def test_production_and_insecure_tokens_rejected(self):
        for kwargs in ({'mode':'production'}, {'demo_token':'short'}, {'admin_token':'x'*40}):
            data={'demo_token':'x'*40,'admin_token':'y'*40,**kwargs}
            with self.assertRaises(ValueError):
                Settings(**data)
