"""API model modes and mock HTTPS adapter use the same authorization pipeline."""
from dataclasses import replace
import json
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

import httpx

from work4ce_assistant.api import Settings, TENANT, create_app
from work4ce_assistant.contracts import CapabilityManifest, ConnectorManifest, Work4ceError
from work4ce_assistant.auth import OIDCConfig
from work4ce_assistant.fixtures import SEARCH_CAPABILITY, search_events
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.models import ModelGateway, OpenAICompatibleProvider
from work4ce_assistant.reasoning import Reasoner
from work4ce_assistant.storage import Store


class Events:
    def __init__(self): self.calls=0
    async def health(self): return True
    async def discover(self): return [SEARCH_CAPABILITY]
    async def invoke(self, capability_id, arguments):
        self.calls+=1
        return search_events(arguments)


class ModelAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.tools=Gateway(self.store)
        self.events=Events()
        await self.tools.register(ConnectorManifest(connector_id='demo-rest',name='demo-rest',protocol='rest',
            tenant_id=TENANT,synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),self.events,reviewed=True)
        self.settings=Settings('x'*40,'y'*40,reasoning_mode='fixture')
        self.app=create_app(self.settings,self.tools)
        self.lifecycle=self.app.router.lifespan_context(self.app)
        await self.lifecycle.__aenter__()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')
        self.headers={'Authorization':'Bearer '+'x'*40}

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifecycle.__aexit__(None,None,None)
        self.store.close()

    async def test_fixture_model_mode_returns_grounded_report_and_scoped_usage(self):
        response=await self.client.post('/investigations',json={'query':'PowerShell'},headers=self.headers)
        self.assertEqual(response.status_code,201,response.text)
        report=response.json()['report']
        self.assertEqual(report['engine'],'structured-fixture-v1')
        self.assertTrue(report['reasoning']['synthetic_fixture'])
        self.assertEqual(report['reasoning']['usage']['calls'],2)
        state=await self.client.get('/investigations/'+response.json()['id']+'/state',headers=self.headers)
        self.assertEqual(state.json()['model_usage']['calls'],2)
        self.assertNotIn('api_key',json.dumps(state.json()))
        self.assertEqual(self.events.calls,1)

    async def test_client_cannot_select_model_route_or_enlarge_budget(self):
        self.assertEqual((await self.client.post('/investigations',json={'query':'PowerShell'},headers={})).status_code,401)
        for extra in ({'reasoning_mode':'provider'},{'model_endpoint':'https://attacker.example/chat/completions'},
                      {'max_model_tokens':999999}):
            response=await self.client.post('/investigations',json={'query':'PowerShell',**extra},headers=self.headers)
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.events.calls,0)

    async def test_mock_https_provider_uses_real_adapter_and_independent_tool_policy(self):
        requests=[]
        async def model(request):
            self.assertEqual(str(request.url),'https://model.example.test/v1/chat/completions')
            self.assertEqual(request.headers['authorization'],'Bearer synthetic-model-credential')
            data=json.loads(request.content)
            self.assertNotIn('synthetic-model-credential',request.content.decode())
            payload=json.loads(data['messages'][1]['content'])
            requests.append(payload)
            if data['response_format']['json_schema']['name']=='work4ce_plan':
                output={'capability_id':'security.events.search','version':'1.0',
                        'arguments':{'query':payload['query'],'limit':payload['limit']}}
            else:
                output={'assessment':'needs_analyst_review','observations':[
                    {'evidence_id':item['evidence_id'],'quote':item['summary']} for item in payload['evidence']]}
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{
                'role':'assistant','content':json.dumps(output)}}],
                'usage':{'prompt_tokens':100,'completion_tokens':100}})
        http=httpx.AsyncClient(transport=httpx.MockTransport(model))
        provider=OpenAICompatibleProvider('https://model.example.test/v1/chat/completions','synthetic-model',
            'synthetic-model-credential',input_price_microusd_per_million=1_000_000,
            output_price_microusd_per_million=2_000_000,client=http)
        reasoner=Reasoner(ModelGateway(provider),self.store)
        app=create_app(replace(self.settings,reasoning_mode='provider',model_allow_synthetic_egress=True,
            model_endpoint=provider.endpoint,model_name=provider.model_name,model_api_key='synthetic-model-credential',
            model_input_price=1_000_000,model_output_price=2_000_000),self.tools,reasoner=reasoner)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
                response=await client.post('/investigations',json={'query':'PowerShell'},headers=self.headers)
            self.assertEqual(response.status_code,201,response.text)
            report=response.json()['report']
            self.assertEqual(report['reasoning']['provider'],'openai-compatible')
            self.assertEqual(report['reasoning']['usage']['actual_cost_microusd'],600)
            self.assertEqual(len(requests),2)
            self.assertEqual(self.events.calls,1)
        finally:
            await reasoner.close()
            await http.aclose()

    def test_provider_startup_requires_explicit_consent_route_prices_and_key(self):
        data={'reasoning_mode':'provider','model_endpoint':'https://model.example.test/v1/chat/completions',
              'model_name':'test','model_api_key':'synthetic-credential','model_allow_synthetic_egress':True,
              'model_input_price':0,'model_output_price':0}
        self.assertEqual(Settings('x'*40,'y'*40,**data).reasoning_mode,'provider')
        for change in ({'model_allow_synthetic_egress':False},{'model_api_key':''},{'model_input_price':None},
                       {'model_endpoint':'http://127.0.0.1/chat/completions'},{'model_endpoint':123},
                       {'model_name':123},{'model_api_key':123},{'model_endpoint':'https://host:invalid/chat/completions'},
                       {'model_endpoint':'https://host/chat/completions#unsafe'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                Settings('x'*40,'y'*40,**{**data,**change})
        self.assertNotIn('synthetic-credential',repr(Settings('x'*40,'y'*40,**data)))

    def test_fixture_environment_needs_no_live_credential_and_budgets_are_validated(self):
        variables={'WORK4CE_DEMO_TOKEN':'x'*40,'WORK4CE_ADMIN_TOKEN':'y'*40,'WORK4CE_REASONING_MODE':'fixture',
                   'WORK4CE_MAX_MODEL_CALLS':'3','WORK4CE_MAX_MODEL_TOKENS':'20000','WORK4CE_MAX_MODEL_COST_MICROUSD':'0'}
        with patch.dict('os.environ',variables,clear=True):
            settings=Settings.from_environment()
        self.assertEqual(settings.model_api_key,'')
        self.assertEqual(settings.max_model_calls,3)
        for change in ({'reasoning_mode':'untrusted'},{'max_model_calls':0},{'max_model_tokens':True},
                       {'max_model_cost_microusd':-1}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                replace(self.settings,**change)

    async def test_cleanup_continues_if_an_owned_client_close_fails(self):
        verifier=SimpleNamespace(close=AsyncMock(side_effect=RuntimeError('controlled cleanup failure')))
        settings=Settings(database=':memory:',reasoning_mode='fixture',auth_mode='oidc',
            oidc_config=OIDCConfig('https://identity.example.test','api','https://identity.example.test/jwks'),
            oidc_subject_roles=(('analyst','analyst'),))
        with patch('work4ce_assistant.api.OIDCVerifier',return_value=verifier), \
             patch.object(Gateway,'register',new=AsyncMock(side_effect=Work4ceError('connector_discovery_failed',503))), \
             patch.object(Reasoner,'close',new=AsyncMock()) as close_reasoner:
            app=create_app(settings)
            with patch.object(app.state.store,'close',wraps=app.state.store.close) as close_store:
                with self.assertRaisesRegex(RuntimeError,'controlled cleanup failure'):
                    async with app.router.lifespan_context(app):
                        self.fail('Bootstrap should fail')
                close_reasoner.assert_awaited_once()
                close_store.assert_called_once()
