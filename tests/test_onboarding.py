"""Setup observations reauthorize, redact failures and never execute inference or tools."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock,patch

import httpx

from work4ce_assistant.api import Settings,create_app,TENANT,PERMISSIONS,CONNECTORS,REVIEWER_PERMISSIONS
from work4ce_assistant.contracts import CapabilityManifest,ConnectorManifest,ExecutionContext
from work4ce_assistant.fixtures import SEARCH_CAPABILITY
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.storage import HEAD,Store


class OnboardingAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.gateway=Gateway(self.store)
        self.adapter=AsyncMock()
        self.adapter.discover.return_value=[SEARCH_CAPABILITY]
        self.adapter.health.return_value=True
        await self.register('demo-rest',self.adapter)
        self.settings=Settings('a'*40,'b'*40,require_human_review=True,reasoning_mode='fixture',
            workflow_max_tool_calls=3,workflow_duration_seconds=60)
        self.app=create_app(self.settings,self.gateway)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')
        self.auth={'Authorization':'Bearer '+'a'*40}
        route=next(route for route in self.app.routes if route.path=='/onboarding/status')
        self.dependency=route.dependant.dependencies[0].call

    async def register(self,identity,adapter,*,tenant=TENANT):
        await self.gateway.register(ConnectorManifest(connector_id=identity,name=identity,protocol='rest',
            tenant_id=tenant,synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),adapter,reviewed=True)

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    async def get(self):
        return await self.client.get('/onboarding/status',headers=self.auth)

    def context(self,permissions=PERMISSIONS,*,tenant=TENANT,synthetic=True,connectors=CONNECTORS):
        self.app.dependency_overrides[self.dependency]=lambda:ExecutionContext(tenant,'actor',permissions,connectors,synthetic)

    async def test_authentication_and_exact_safe_read_only_contract(self):
        self.assertEqual((await self.client.get('/onboarding/status')).status_code,401)
        before=self.store.audit_rows(TENANT)
        response=await self.get()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json(),{
            'mode':'demo','synthetic':True,'production_enabled':False,
            'authentication':{'mode':'demo','administrator_configured':True},
            'database':{'status':'ready','schema_revision':HEAD},
            'reasoning':{'mode':'fixture','health_checked':False},
            'policy':{'review_required':True,'response_mode':'simulation_only','max_tool_calls':3,'timeout_seconds':60},
            'connectors':[{'connector_id':'demo-rest','protocol':'rest','enabled':True,'synthetic':True,'health':'healthy'}],
            'can_investigate':True,'ready_for_investigation':True})
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(self.store.audit_rows(TENANT),before)
        self.adapter.invoke.assert_not_awaited()
        self.adapter.discover.assert_awaited_once()
        for secret in ('a'*40,'b'*40,self.settings.database,self.settings.rest_url,'model_api_key','oidc_subject_roles'):
            self.assertNotIn(secret,response.text)
        self.assertEqual((await self.client.post('/onboarding/status',headers=self.auth,json={'mode':'production'})).status_code,405)

    async def test_current_permissions_restrict_launch_and_setup_read(self):
        self.context(REVIEWER_PERMISSIONS)
        data=(await self.get()).json()
        self.assertFalse(data['can_investigate'])
        self.assertFalse(data['ready_for_investigation'])
        self.assertEqual(data['connectors'][0]['health'],'healthy')
        for missing in ('investigations:run','events:read'):
            self.context(PERMISSIONS-{missing})
            data=(await self.get()).json()
            self.assertFalse(data['can_investigate'])
            self.assertFalse(data['ready_for_investigation'])
        self.context(PERMISSIONS-{'investigations:read'})
        self.assertEqual((await self.get()).status_code,403)

    async def test_foreign_and_nonsynthetic_context_cannot_probe(self):
        for tenant,synthetic in (('foreign',True),(TENANT,False)):
            self.context(tenant=tenant,synthetic=synthetic)
            self.assertEqual((await self.get()).status_code,403)
        self.adapter.health.assert_not_awaited()

    async def test_only_current_authorized_integrity_valid_sources_are_probed(self):
        hidden=AsyncMock()
        hidden.discover.return_value=[SEARCH_CAPABILITY]
        hidden.health.return_value=True
        await self.register('hidden-source',hidden)
        self.context(connectors=frozenset())
        data=(await self.get()).json()
        self.assertEqual(data['connectors'],[])
        self.assertFalse(data['ready_for_investigation'])
        self.context()
        self.gateway._entries['demo-rest'].manifest.capability.input_schema['injected']=True
        data=(await self.get()).json()
        self.assertEqual(data['connectors'],[])
        self.assertFalse(data['ready_for_investigation'])
        self.adapter.health.assert_not_awaited()
        hidden.health.assert_not_awaited()

    async def test_disable_is_observed_without_probing_disabled_source(self):
        self.store.disable(TENANT,'admin','demo-rest')
        data=(await self.get()).json()
        self.assertFalse(data['ready_for_investigation'])
        self.assertEqual(data['connectors'][0]['health'],'disabled')
        self.assertFalse(data['connectors'][0]['enabled'])
        self.adapter.health.assert_not_awaited()

    async def test_unhealthy_peer_does_not_hide_a_healthy_fallback_and_errors_are_redacted(self):
        broken=AsyncMock()
        broken.discover.return_value=[SEARCH_CAPABILITY]
        broken.health.side_effect=RuntimeError('credential-sensitive-route')
        await self.register('demo-mcp',broken)
        response=await self.get()
        self.assertTrue(response.json()['ready_for_investigation'])
        self.assertEqual([row['health'] for row in response.json()['connectors']],['healthy','unhealthy'])
        self.assertNotIn('credential-sensitive-route',response.text)
        self.adapter.health.return_value=False
        self.assertFalse((await self.get()).json()['ready_for_investigation'])
        broken.invoke.assert_not_awaited()

    async def test_database_failure_is_redacted_and_never_ready(self):
        with patch.object(self.store,'_connection',side_effect=RuntimeError('database-password-secret')):
            response=await self.get()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['database'],{'status':'unavailable','schema_revision':None})
        self.assertFalse(response.json()['ready_for_investigation'])
        self.assertNotIn('database-password-secret',response.text)
        self.adapter.health.assert_not_awaited()

    async def test_schema_drift_is_not_reported_as_ready_or_disclosed(self):
        with self.store.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='unrecognized-private-value'")
        response=await self.get()
        self.assertEqual(response.json()['database'],{'status':'unavailable','schema_revision':None})
        self.assertFalse(response.json()['ready_for_investigation'])
        self.assertNotIn('unrecognized-private-value',response.text)

    async def test_health_probe_timeout_is_bounded_without_invocation(self):
        async def slow():
            await asyncio.Event().wait()
        self.adapter.health.side_effect=slow
        async with asyncio.timeout(4):
            data=(await self.get()).json()
        self.assertEqual(data['connectors'][0]['health'],'unhealthy')
        self.assertFalse(data['ready_for_investigation'])
        self.adapter.invoke.assert_not_awaited()

    async def test_request_parameters_cannot_override_observations(self):
        response=await self.client.get('/onboarding/status?mode=production&review_required=false&ready_for_investigation=true',headers=self.auth)
        self.assertEqual(response.json()['mode'],'demo')
        self.assertTrue(response.json()['policy']['review_required'])
        self.context(connectors=frozenset())
        response=await self.client.get('/onboarding/status?ready_for_investigation=true',headers=self.auth)
        self.assertFalse(response.json()['ready_for_investigation'])

    async def test_provider_configuration_is_reported_without_a_model_call_or_route(self):
        from dataclasses import replace
        settings=replace(self.settings,reasoning_mode='provider',model_endpoint='https://sensitive-provider.test/v1/chat/completions',
            model_name='private-model-name',model_api_key='private-provider-key',model_allow_synthetic_egress=True,
            model_input_price=123,model_output_price=456)
        reasoner=AsyncMock()
        reasoner.store=self.store
        app=create_app(settings,self.gateway,reasoner=reasoner)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            response=await client.get('/onboarding/status',headers=self.auth)
        self.assertEqual(response.json()['reasoning'],{'mode':'provider','health_checked':False})
        self.assertTrue(response.json()['ready_for_investigation'])
        self.assertEqual(reasoner.mock_calls,[])
        self.adapter.invoke.assert_not_awaited()
        for secret in ('sensitive-provider.test','private-model-name','private-provider-key','model_input_price','model_output_price'):
            self.assertNotIn(secret,response.text)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'),'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL setup observation unrun')
class PostgreSQLOnboardingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import test_storage
        test_storage.PostgreSQLStoreTests.setUp(self)

    async def asyncTearDown(self):
        import test_storage
        test_storage.PostgreSQLStoreTests.tearDown(self)

    async def test_migrated_database_and_durable_connector_revocation(self):
        adapter=AsyncMock()
        adapter.discover.return_value=[SEARCH_CAPABILITY]
        adapter.health.return_value=True
        gateway=Gateway(self.store)
        await gateway.register(ConnectorManifest(connector_id='demo-rest',name='Demo',protocol='rest',tenant_id=TENANT,
            synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),adapter,reviewed=True)
        app=create_app(Settings('a'*40,'b'*40),gateway)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            auth={'Authorization':'Bearer '+'a'*40}
            data=(await client.get('/onboarding/status',headers=auth)).json()
            self.assertEqual(data['database'],{'status':'ready','schema_revision':HEAD})
            self.assertTrue(data['ready_for_investigation'])
            self.store.disable(TENANT,'manager','demo-rest')
            data=(await client.get('/onboarding/status',headers=auth)).json()
            self.assertEqual(data['connectors'][0]['health'],'disabled')
            self.assertFalse(data['ready_for_investigation'])
            adapter.health.assert_awaited_once()
            adapter.invoke.assert_not_awaited()


if __name__=='__main__': unittest.main()
