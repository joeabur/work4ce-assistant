"""Administrator activation validates trusted definitions without executing tools."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import AsyncMock,patch

import httpx

from work4ce_assistant.api import Settings,create_app,TENANT,PERMISSIONS,CONNECTORS,REVIEWER_PERMISSIONS
from work4ce_assistant.connector_admin import ConnectorAdministration
from work4ce_assistant.contracts import CapabilityManifest,ConnectorManifest,ExecutionContext,Work4ceError
from work4ce_assistant.fixtures import SEARCH_CAPABILITY,search_events
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.storage import Store


class ConnectorAdministrationAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.gateway=Gateway(self.store)
        self.adapter=AsyncMock()
        self.adapter.discover.return_value=[deepcopy(SEARCH_CAPABILITY)]
        self.adapter.health.return_value=True
        self.adapter.invoke.side_effect=lambda _,arguments:search_events(arguments)
        self.manifest=ConnectorManifest(connector_id='demo-rest',name='Demo',protocol='rest',tenant_id=TENANT,
            synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY))
        await self.gateway.register(self.manifest,self.adapter,reviewed=True)
        self.app=create_app(Settings('a'*40,'b'*40),self.gateway)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')
        self.admin={'Authorization':'Bearer '+'b'*40}
        self.analyst={'Authorization':'Bearer '+'a'*40}
        self.base='/connectors/demo-rest/administration'
        self.hash=self.gateway._entries['demo-rest'].manifest_hash
        self.service=ConnectorAdministration(self.gateway)
        self.context=ExecutionContext(TENANT,'demo-admin',PERMISSIONS|{'connectors:admin'},CONNECTORS,True)

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    async def state(self):
        response=await self.client.get('/connectors/administration',headers=self.admin)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()[0]

    async def disable(self,revision=0):
        return await self.client.post(self.base+'/disable',headers=self.admin,
            json={'expected_revision':revision,'reason':'Disable this synthetic source.'})

    async def enable(self,revision=1,**updates):
        return await self.client.post(self.base+'/review-enable',headers=self.admin,
            json={'expected_revision':revision,'manifest_hash':self.hash,'reason':'Reviewed the pinned synthetic read contract.',**updates})

    async def test_scoped_admin_projection_and_legacy_array_remain_private_and_read_only(self):
        self.assertEqual((await self.client.get('/connectors/administration')).status_code,401)
        self.assertEqual((await self.client.get('/connectors/administration',headers=self.analyst)).status_code,403)
        response=await self.client.get('/connectors/administration',headers=self.admin)
        item=response.json()[0]
        self.assertEqual(item['manifest_hash'],self.hash)
        self.assertEqual(item['revision'],0)
        self.assertIsNone(item['last_change'])
        self.assertIsNone(item['last_review'])
        self.assertEqual(item['required_permissions'],['events:read'])
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertFalse({'input_schema','output_schema','token','endpoint','tenant_id'} & item.keys())
        legacy=(await self.client.get('/connectors',headers=self.analyst)).json()
        self.assertEqual(set(legacy[0]),{'connector_id','protocol','enabled','synthetic'})
        self.adapter.invoke.assert_not_awaited()
        self.adapter.health.assert_not_awaited()

    async def test_disable_review_enable_retains_exact_hash_actor_reason_and_restores_execution(self):
        disabled=await self.disable()
        self.assertEqual(disabled.status_code,200,disabled.text)
        self.assertFalse(disabled.json()['enabled'])
        self.assertEqual((await self.client.get('/ready',headers=self.analyst)).status_code,503)
        reason='<img src=x onerror=alert(1)> Reviewed synthetic scope.'
        enabled=await self.enable(reason=reason)
        self.assertEqual(enabled.status_code,200,enabled.text)
        data=enabled.json()
        self.assertEqual(data['revision'],2)
        self.assertEqual(data['last_review'],{'manifest_hash':self.hash,'actor':'demo-admin',
            'at':data['last_change']['at'],'reason':reason})
        self.assertEqual(data['last_change']['reason'],reason)
        self.assertTrue((await self.client.get('/onboarding/status',headers=self.analyst)).json()['ready_for_investigation'])
        self.adapter.invoke.assert_not_awaited()
        result=await self.client.post('/investigations',headers=self.analyst,json={'query':'PowerShell'})
        self.assertEqual(result.status_code,201,result.text)
        self.assertEqual(result.json()['report']['evidence'][0]['connector_id'],'demo-rest')

    async def test_nonadmin_and_unpermitted_contexts_cannot_mutate_or_probe(self):
        for suffix,body in (('/disable',{'expected_revision':0,'reason':'Denied'}),
            ('/review-enable',{'expected_revision':0,'manifest_hash':self.hash,'reason':'Denied'})):
            response=await self.client.post(self.base+suffix,headers=self.analyst,json=body)
            self.assertEqual(response.status_code,403,response.text)
        for ctx in (replace(self.context,tenant_id='foreign'),replace(self.context,synthetic=False),
                    replace(self.context,allowed_connectors=frozenset())):
            self.assertEqual(self.service.list(ctx),[])
            with self.assertRaisesRegex(Work4ceError,'connector_not_found'):
                await self.service.review_enable(ctx,'demo-rest',0,self.hash,'Denied')
        with self.assertRaisesRegex(Work4ceError,'permission_denied'):
            self.service.list(replace(self.context,permissions=REVIEWER_PERMISSIONS))
        self.adapter.health.assert_not_awaited()
        self.adapter.discover.assert_awaited_once()
        self.assertEqual((await self.state())['revision'],0)

    async def test_stale_revision_hash_and_invalid_body_do_not_probe_or_enable(self):
        self.assertEqual((await self.disable()).status_code,200)
        for body in ({'expected_revision':0},{'manifest_hash':'0'*64},{'expected_revision':True},
                     {'reason':'   '},{'reason':'x'*1001},{'manifest_hash':'bad'},
                     {'actor':'forged'},{'enabled':True}):
            response=await self.enable(**body)
            self.assertIn(response.status_code,(409,422),response.text)
        self.assertFalse((await self.state())['enabled'])
        self.adapter.health.assert_not_awaited()
        self.adapter.discover.assert_awaited_once()

    async def test_discovery_definition_changes_and_private_errors_leave_source_disabled(self):
        await self.disable()
        self.adapter.discover.side_effect=RuntimeError('private-discovery-secret')
        response=await self.enable()
        self.assertEqual(response.json(),{'error':'connector_discovery_failed'})
        self.assertEqual(response.status_code,503)
        self.adapter.discover.side_effect=None
        changed=deepcopy(SEARCH_CAPABILITY)
        changed['description']='Changed after trusted registration'
        for result in ([],[SEARCH_CAPABILITY,SEARCH_CAPABILITY],[changed],[{'invalid':'definition'}]):
            self.adapter.discover.return_value=result
            response=await self.enable()
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(response.json(),{'error':'connector_contract_mismatch'})
        self.adapter.health.assert_not_awaited()
        self.assertFalse((await self.state())['enabled'])

    async def test_unhealthy_or_error_health_never_activates_and_redacts_diagnostics(self):
        await self.disable()
        for health in (False,'true',None):
            self.adapter.health.return_value=health
            response=await self.enable()
            self.assertEqual(response.status_code,503,response.text)
            self.assertEqual(response.json(),{'error':'connector_unhealthy'})
        self.adapter.health.side_effect=RuntimeError('private-health-secret')
        response=await self.enable()
        self.assertEqual(response.json(),{'error':'connector_unhealthy'})
        self.assertNotIn('private-health-secret',response.text)
        self.assertFalse((await self.state())['enabled'])
        self.adapter.invoke.assert_not_awaited()

    async def test_disable_during_validation_fences_even_a_repeated_legacy_disable(self):
        await self.disable()
        entered,release=asyncio.Event(),asyncio.Event()
        async def health():
            entered.set()
            await release.wait()
            return True
        self.adapter.health.side_effect=health
        task=asyncio.create_task(self.enable())
        await asyncio.wait_for(entered.wait(),1)
        legacy=await self.client.post('/connectors/demo-rest/disable',headers=self.admin)
        self.assertEqual(legacy.json(),{'connector_id':'demo-rest','enabled':False})
        release.set()
        response=await task
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json(),{'error':'connector_revision_conflict'})
        self.assertFalse((await self.state())['enabled'])

    async def test_pinned_manifest_mutation_during_health_fails_closed(self):
        await self.disable()
        async def health():
            self.gateway._entries['demo-rest'].manifest.capability.input_schema['tampered']=True
            return True
        self.adapter.health.side_effect=health
        response=await self.enable()
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json(),{'error':'connector_definition_changed'})
        self.assertFalse(self.store.connector_administration(TENANT,'demo-rest')['enabled'])

    async def test_cancelled_validation_does_not_commit_state_or_audit(self):
        await self.disable()
        entered=asyncio.Event()
        async def health():
            entered.set()
            await asyncio.Event().wait()
        self.adapter.health.side_effect=health
        before=self.store.audit_rows(TENANT)
        task=asyncio.create_task(self.service.review_enable(self.context,'demo-rest',1,self.hash,'Review'))
        await asyncio.wait_for(entered.wait(),1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertFalse((await self.state())['enabled'])
        self.assertEqual(self.store.audit_rows(TENANT),before)

    async def test_review_metadata_and_enable_roll_back_with_audit_failure(self):
        await self.disable()
        before=await self.state()
        with patch.object(self.store,'_audit',side_effect=RuntimeError('controlled rollback')):
            with self.assertRaisesRegex(RuntimeError,'controlled rollback'):
                await self.service.review_enable(self.context,'demo-rest',1,self.hash,'Review')
        self.assertEqual(await self.state(),before)

    async def test_trusted_reregistration_cannot_reuse_a_review_for_a_changed_manifest(self):
        await self.disable()
        self.assertEqual((await self.enable()).status_code,200)
        restarted=Gateway(self.store)
        changed=self.manifest.model_copy(update={'name':'Changed trusted manifest'})
        await restarted.register(changed,self.adapter,reviewed=True)
        self.assertTrue(self.store.connector_administration(TENANT,'demo-rest')['enabled'])
        self.assertFalse(restarted.list_connectors(self.context)[0]['enabled'])
        self.assertEqual(restarted.capabilities(self.context),[])
        with self.assertRaisesRegex(Work4ceError,'no_authorized_connector'):
            await restarted.execute(self.context,'security.events.search',{'query':'PowerShell'})
        service=ConnectorAdministration(restarted)
        current=service.list(self.context)[0]
        self.assertNotEqual(current['manifest_hash'],current['last_review']['manifest_hash'])
        service.disable(self.context,'demo-rest',2,'Disable outdated review')
        await service.review_enable(self.context,'demo-rest',3,current['manifest_hash'],'Review changed definition')
        self.assertTrue(restarted.list_connectors(self.context)[0]['enabled'])

    async def test_discovery_and_health_timeouts_are_bounded_without_activation(self):
        adapter=AsyncMock()
        definition={**deepcopy(SEARCH_CAPABILITY),'timeout_seconds':0.01}
        adapter.discover.return_value=[definition]
        adapter.health.return_value=True
        gateway=Gateway(self.store)
        await gateway.register(self.manifest.model_copy(update={'capability':CapabilityManifest(**definition)}),adapter,reviewed=True)
        service=ConnectorAdministration(gateway)
        service.disable(self.context,'demo-rest',0,'Timeout checks')
        current=service.list(self.context)[0]
        async def stalled(): await asyncio.Event().wait()
        adapter.discover.side_effect=stalled
        async with asyncio.timeout(1):
            with self.assertRaisesRegex(Work4ceError,'connector_discovery_failed'):
                await service.review_enable(self.context,'demo-rest',1,current['manifest_hash'],'Review timeout')
        adapter.health.assert_not_awaited()
        adapter.discover.side_effect=None
        adapter.health.side_effect=stalled
        async with asyncio.timeout(1):
            with self.assertRaisesRegex(Work4ceError,'connector_unhealthy'):
                await service.review_enable(self.context,'demo-rest',1,current['manifest_hash'],'Review timeout')
        self.assertFalse(self.store.connector_administration(TENANT,'demo-rest')['enabled'])
        adapter.invoke.assert_not_awaited()


if __name__=='__main__': unittest.main()
