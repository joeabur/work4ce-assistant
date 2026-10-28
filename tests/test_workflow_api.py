"""Authenticated workflow HTTP controls and trusted budget configuration."""
import unittest
from unittest.mock import patch

import httpx

from work4ce_assistant.api import Settings, TENANT, create_app
from work4ce_assistant.contracts import CapabilityManifest, ConnectorManifest
from work4ce_assistant.fixtures import SEARCH_CAPABILITY, search_events
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.storage import Store


class Adapter:
    def __init__(self):
        self.calls = 0
    async def discover(self):
        return [SEARCH_CAPABILITY]
    async def health(self):
        return True
    async def invoke(self, capability_id, arguments):
        self.calls += 1
        return search_events(arguments)


class WorkflowAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = Store(':memory:')
        self.gateway = Gateway(self.store)
        self.adapter = Adapter()
        await self.gateway.register(ConnectorManifest(connector_id='demo-rest',name='demo-rest',protocol='rest',
            tenant_id=TENANT,synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),self.adapter,reviewed=True)
        self.settings = Settings('x'*40,'y'*40,workflow_max_tool_calls=1,workflow_duration_seconds=60)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.settings,self.gateway)),base_url='http://api')
        self.auth={'Authorization':'Bearer '+self.settings.demo_token}
        self.admin={'Authorization':'Bearer '+self.settings.admin_token}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    async def test_queue_resume_replay_and_owner_scope(self):
        headers={**self.auth,'Idempotency-Key':'http-key'}
        queued=await self.client.post('/investigations',json={'query':'PowerShell','defer':True},headers=headers)
        self.assertEqual(queued.status_code,202,queued.text)
        identity=queued.json()['id']
        state=(await self.client.get('/investigations/'+identity+'/state',headers=self.auth)).json()
        self.assertEqual(state['status'],'queued')
        self.assertEqual(state['max_tool_calls'],1)
        self.assertEqual(state['tool_calls'],0)
        self.assertEqual(self.adapter.calls,0)
        for endpoint in ('state','resume','cancel'):
            operation=self.client.get if endpoint=='state' else self.client.post
            self.assertEqual((await operation('/investigations/'+identity+'/'+endpoint,headers=self.admin)).status_code,404)
            self.assertEqual((await operation('/investigations/'+identity+'/'+endpoint)).status_code,401)
        result=await self.client.post('/investigations/'+identity+'/resume',headers=self.auth)
        self.assertEqual(result.status_code,200,result.text)
        replay=await self.client.post('/investigations',json={'query':'PowerShell'},headers=headers)
        self.assertEqual(replay.json(),result.json())
        self.assertEqual(self.adapter.calls,1)
        state=(await self.client.get('/investigations/'+identity+'/state',headers=self.auth)).json()
        self.assertEqual(state['tool_calls'],1)
        self.assertTrue(state['checkpointed'])
        self.assertFalse({'idempotency_key','lease_owner','checkpoint','query'} & state.keys())

    async def test_http_quota_and_cancellation(self):
        for i in range(100):
            queued=await self.client.post('/investigations',json={'query':'PowerShell','defer':True},
                headers={**self.auth,'Idempotency-Key':f'quota-{i}'})
            self.assertEqual(queued.status_code,202,queued.text)
        replay=await self.client.post('/investigations',json={'query':'PowerShell','defer':True},
            headers={**self.auth,'Idempotency-Key':'quota-0'})
        self.assertEqual(replay.status_code,202)
        full=await self.client.post('/investigations',json={'query':'PowerShell','defer':True},headers=self.auth)
        self.assertEqual(full.status_code,429,full.text)
        self.assertEqual(full.json(),{'error':'workflow_queue_full'})
        identity=replay.json()['id']
        cancelled=await self.client.post('/investigations/'+identity+'/cancel',headers=self.auth)
        self.assertEqual(cancelled.json()['status'],'cancelled')
        self.assertEqual((await self.client.post('/investigations/'+identity+'/resume',headers=self.auth)).status_code,409)
        available=await self.client.post('/investigations',json={'query':'PowerShell','defer':True},headers=self.auth)
        self.assertEqual(available.status_code,202)
        self.assertEqual(self.adapter.calls,0)

    async def test_untrusted_limits_and_malformed_idempotency_rejected(self):
        for body,headers in (({'query':'x','max_tool_calls':100},self.auth),
                ({'query':'x'},{**self.auth,'Idempotency-Key':'invalid key'}),
                ({'query':'x'},{**self.auth,'Idempotency-Key':'k'*129})):
            response=await self.client.post('/investigations',json=body,headers=headers)
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.adapter.calls,0)

    def test_budget_environment_is_trusted_and_validated(self):
        variables={'WORK4CE_DEMO_TOKEN':'x'*40,'WORK4CE_ADMIN_TOKEN':'y'*40,
            'WORK4CE_MAX_TOOL_CALLS':'3','WORK4CE_INVESTIGATION_TIMEOUT_SECONDS':'90'}
        with patch.dict('os.environ',variables,clear=True):
            settings=Settings.from_environment()
        self.assertEqual(settings.workflow_max_tool_calls,3)
        self.assertEqual(settings.workflow_duration_seconds,90)
        for calls,timeout in ((0,120),(9,120),(2,float('nan')),(2,601),(True,120)):
            with self.subTest(calls=calls,timeout=timeout),self.assertRaises(ValueError):
                Settings('x'*40,'y'*40,workflow_max_tool_calls=calls,workflow_duration_seconds=timeout)
