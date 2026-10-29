"""Model assistance integration/security tests with synthetic providers only."""
import asyncio
from dataclasses import replace
import unittest
from unittest.mock import patch

from work4ce_assistant.api import CONNECTORS, PERMISSIONS, TENANT
from work4ce_assistant.contracts import CapabilityManifest, ConnectorManifest, ExecutionContext, Work4ceError
from work4ce_assistant.fixtures import SEARCH_CAPABILITY, search_events
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.investigation import Investigator
from work4ce_assistant.models import FixtureProvider, ModelGateway, ModelProviderError, ModelResult
from work4ce_assistant.reasoning import Reasoner
from work4ce_assistant.storage import Store


def context(**changes):
    return replace(ExecutionContext(TENANT,'analyst',PERMISSIONS,CONNECTORS,True),**changes)


class Events:
    def __init__(self):
        self.calls=0
        self.interrupt=False
    async def health(self): return True
    async def discover(self): return [SEARCH_CAPABILITY]
    async def invoke(self, capability_id, arguments):
        self.calls+=1
        if self.interrupt:
            self.interrupt=False
            raise asyncio.CancelledError
        return search_events(arguments)


class ScriptedProvider(FixtureProvider):
    def __init__(self, *, plan=None, assessment=None, transient=0):
        self.calls=0
        self.plan_output=plan
        self.assessment_output=assessment
        self.transient=transient
        self.interrupt=False
    async def generate(self, request):
        self.calls+=1
        if self.interrupt:
            self.interrupt=False
            raise asyncio.CancelledError
        if self.transient:
            self.transient-=1
            raise ModelProviderError(True)
        result=await super().generate(request)
        output=(self.plan_output if request.stage=='plan' else self.assessment_output)
        return ModelResult(result.output if output is None else output,result.input_tokens,result.output_tokens,
                           self.provider_name,self.model_name)


class ReasoningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.events=Events()
        self.tools=Gateway(self.store)
        await self.tools.register(ConnectorManifest(connector_id='demo-rest',name='demo-rest',protocol='rest',
            tenant_id=TENANT,synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),self.events,reviewed=True)
        self.provider=ScriptedProvider()
        self.reasoner=Reasoner(ModelGateway(self.provider),self.store)
        self.agent=Investigator(self.tools,self.store,reasoner=self.reasoner)

    async def asyncTearDown(self):
        await self.reasoner.close()
        self.store.close()

    async def test_fixture_path_is_grounded_labelled_and_usage_is_durable(self):
        result=await self.agent.investigate(context(),'PowerShell',idempotency_key='model-fixture')
        report=result['report']
        self.assertEqual(report['engine'],'structured-fixture-v1')
        self.assertTrue(report['reasoning']['synthetic_fixture'])
        self.assertEqual(report['reasoning']['usage']['calls'],2)
        self.assertEqual(report['reasoning']['usage']['reserved_tokens'],2*(8192+512))
        self.assertEqual(report['reasoning']['usage']['actual_cost_microusd'],0)
        self.assertGreater(report['reasoning']['usage']['actual_input_tokens'],0)
        sources={e['evidence_id']:e for e in report['evidence']}
        for finding in report['findings']:
            source=sources[finding['evidence_ids'][0]]
            self.assertEqual(finding['statement'],'Observed synthetic telemetry: '+source['content']['summary'])
        self.assertEqual(self.events.calls,1)
        self.assertEqual(self.provider.calls,2)
        self.assertEqual(await self.agent.investigate(context(),'PowerShell',idempotency_key='model-fixture'),result)
        self.assertEqual(self.provider.calls,2)

    async def test_plan_cannot_expand_query_or_tool_scope(self):
        for output in ({'capability_id':'security.response.execute','version':'1.0','arguments':{'query':'PowerShell','limit':20}},
                       {'capability_id':'security.events.search','version':'1.0','arguments':{'query':'*','limit':20}},
                       {'capability_id':'security.events.search','version':'1.0','arguments':{'query':'PowerShell','limit':100}}):
            self.provider.plan_output=output
            with self.subTest(output=output),self.assertRaises(Work4ceError):
                await self.agent.investigate(context(),'PowerShell')
        self.assertEqual(self.events.calls,0)

    async def test_hallucinated_ids_quotes_and_unsupported_verdicts_fail_closed(self):
        for output in ({'assessment':'confirmed_malicious','observations':[]},
                       {'assessment':'needs_analyst_review','observations':[]},
                       {'assessment':'needs_analyst_review','observations':[{'evidence_id':'invented','quote':'invented fact'}]}):
            self.provider.assessment_output=output
            state=self.agent.enqueue(context(),'PowerShell')
            with self.subTest(output=output),self.assertRaises(Work4ceError):
                await self.agent.resume(context(),state['id'])
            report=self.store.get(TENANT,state['id'])
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['report']['findings'],[])
            self.assertIsNotNone(self.store.get_workflow(TENANT,'analyst',state['id'])['checkpoint'])

    async def test_valid_id_with_invented_or_partial_quote_rejected(self):
        original=self.provider.generate
        async def forged(request):
            if request.stage=='plan': return await original(request)
            source=request.payload['evidence'][0]
            return ModelResult({'assessment':'needs_analyst_review','observations':[
                {'evidence_id':source['evidence_id'],'quote':'PowerShell'}]},10,10,'fixture','fixture-v1')
        self.provider.generate=forged
        with self.assertRaisesRegex(Work4ceError,'model_evidence_rejected'):
            await self.agent.investigate(context(),'PowerShell')

    async def test_model_cannot_gain_connector_permissions(self):
        for ctx in (context(permissions=frozenset({'investigations:run'})),context(allowed_connectors=frozenset())):
            with self.subTest(ctx=ctx),self.assertRaises(Work4ceError):
                await self.agent.investigate(ctx,'PowerShell')
        self.assertEqual(self.provider.calls,0)
        self.assertEqual(self.events.calls,0)

    async def test_recognizable_secret_like_input_not_sent_to_provider(self):
        for query in ('password=do-not-send','Bearer synthetic-test-token-123456789','api_key=synthetic-secret'):
            with self.subTest(query=query),self.assertRaisesRegex(Work4ceError,'model_sensitive_input'):
                await self.agent.investigate(context(),query)
        self.assertEqual(self.provider.calls,0)

    async def test_retries_reserve_every_actual_attempt(self):
        self.provider.transient=1
        report=(await self.agent.investigate(context(),'PowerShell'))['report']
        self.assertEqual(self.provider.calls,3)
        self.assertEqual(report['reasoning']['usage']['calls'],3)
        self.assertEqual(report['reasoning']['usage']['reserved_tokens'],3*8704)

    async def test_cancellation_keeps_reservation_and_resume_cannot_reset_budget(self):
        self.provider.interrupt=True
        with self.assertRaises(asyncio.CancelledError):
            await self.agent.investigate(context(),'PowerShell',idempotency_key='cancel-provider')
        state=self.agent.enqueue(context(),'PowerShell',idempotency_key='cancel-provider')
        self.assertEqual(self.store.model_usage(TENANT,'analyst',state['id'])['calls'],1)
        report=(await self.agent.resume(context(),state['id']))['report']
        self.assertEqual(report['reasoning']['usage']['calls'],3)
        self.assertEqual(self.provider.calls,3)

    async def test_call_token_and_cost_limits_reject_before_provider_invocation(self):
        for budgets in ({'max_calls':1},{'max_tokens':100},{'max_cost_microusd':0}):
            provider=ScriptedProvider()
            if 'max_cost_microusd' in budgets:
                provider.input_price_microusd_per_million=1_000_000
                provider.output_price_microusd_per_million=1_000_000
            reasoner=Reasoner(ModelGateway(provider),self.store,**budgets)
            agent=Investigator(self.tools,self.store,reasoner=reasoner)
            with self.subTest(budgets=budgets),self.assertRaisesRegex(Work4ceError,'model_budget_exhausted'):
                await agent.investigate(context(),'PowerShell')
            self.assertEqual(provider.calls,1 if 'max_calls' in budgets else 0)

    async def test_crash_after_planning_reuses_plan_without_another_model_call(self):
        self.events.interrupt=True
        with self.assertRaises(asyncio.CancelledError):
            await self.agent.investigate(context(),'PowerShell',idempotency_key='cached-plan')
        state=self.agent.enqueue(context(),'PowerShell',idempotency_key='cached-plan')
        result=await self.agent.resume(context(),state['id'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(self.provider.calls,2)
        self.assertEqual(self.events.calls,2)

    async def test_crash_after_assessment_reuses_results_and_evidence(self):
        with patch.object(self.store,'finish_workflow',side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await self.agent.investigate(context(),'PowerShell',idempotency_key='cached-models')
        state=self.agent.enqueue(context(),'PowerShell',idempotency_key='cached-models')
        checkpoint=state['checkpoint']
        result=await self.agent.resume(context(),state['id'])
        self.assertEqual(result['report']['evidence'],checkpoint['evidence'])
        self.assertEqual(self.provider.calls,2)
        self.assertEqual(self.events.calls,1)

    async def test_mode_or_route_change_requires_original_configuration(self):
        state=self.agent.enqueue(context(),'PowerShell',idempotency_key='frozen-model')
        with self.assertRaisesRegex(Work4ceError,'model_configuration_changed'):
            await Investigator(self.tools,self.store).resume(context(),state['id'])
        other=ScriptedProvider()
        other.model_name='another-fixture'
        changed=Investigator(self.tools,self.store,reasoner=Reasoner(ModelGateway(other),self.store))
        with self.assertRaisesRegex(Work4ceError,'model_configuration_changed'):
            await changed.resume(context(),state['id'])
        with self.assertRaisesRegex(Work4ceError,'idempotency_conflict'):
            changed.enqueue(context(),'PowerShell',idempotency_key='frozen-model')
        self.assertEqual((await self.agent.resume(context(),state['id']))['status'],'completed')

    async def test_different_provider_uses_same_investigator_and_policy(self):
        provider=ScriptedProvider()
        provider.provider_name='second-fixture-contract'
        provider.model_name='second-model'
        reasoner=Reasoner(ModelGateway(provider),self.store)
        result=await Investigator(self.tools,self.store,reasoner=reasoner).investigate(context(),'PowerShell')
        self.assertEqual(result['report']['reasoning']['provider'],'second-fixture-contract')
        self.assertEqual(provider.calls,2)
        self.assertEqual(self.events.calls,1)
