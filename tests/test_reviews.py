"""Independent review/approval policy; every response is a synthetic dry run."""
from dataclasses import replace
import tempfile
from pathlib import Path
import time
import unittest
from uuid import uuid4
from unittest.mock import patch

import httpx
from sqlalchemy import update

from work4ce_assistant.api import (Settings,create_app,TENANT,PERMISSIONS,ADMIN_PERMISSIONS,
                                   REVIEWER_PERMISSIONS,CONNECTORS)
from work4ce_assistant.contracts import CapabilityManifest,ConnectorManifest,ExecutionContext,Work4ceError
from work4ce_assistant.fixtures import SEARCH_CAPABILITY,search_events
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.investigation import Investigator
from work4ce_assistant.reviews import ReviewService
from work4ce_assistant.storage import Store,response_approvals


def owner(**updates):
    return replace(ExecutionContext(TENANT,'analyst',PERMISSIONS,CONNECTORS,True),**updates)


def reviewer(**updates):
    return replace(ExecutionContext(TENANT,'reviewer',REVIEWER_PERMISSIONS,CONNECTORS,True),**updates)


class Events:
    def __init__(self): self.calls=0
    async def health(self): return True
    async def discover(self): return [SEARCH_CAPABILITY]
    async def invoke(self,capability_id,arguments):
        self.calls+=1
        return search_events(arguments)


async def tools_for(store,events):
    tools=Gateway(store)
    await tools.register(ConnectorManifest(connector_id='demo-rest',name='demo-rest',protocol='rest',tenant_id=TENANT,
        synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),events,reviewed=True)
    return tools


class ReviewPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.events=Events()
        self.tools=await tools_for(self.store,self.events)
        self.agent=Investigator(self.tools,self.store,require_review=True)
        self.service=ReviewService(self.store,self.tools)
        self.result=await self.agent.investigate(owner(),'PowerShell')
        self.identity=self.result['id']

    async def asyncTearDown(self): self.store.close()

    def accept(self):
        review=self.service.get_review(owner(),self.identity)
        return self.service.decide_review(reviewer(),self.identity,review['review_id'],'approved')

    def proposal(self):
        return self.service.propose(owner(),self.identity,'endpoint.isolate','demo-host-1',{'duration_minutes':15})

    def approved(self):
        self.accept()
        proposal=self.proposal()
        return self.service.decide_response(reviewer(),proposal['id'],'approved')

    async def test_durable_review_gate_and_separation_of_duties(self):
        self.assertEqual(self.result['status'],'awaiting_review')
        self.assertEqual(self.result['review']['state'],'pending')
        self.assertEqual((await self.agent.resume(owner(),self.identity))['status'],'awaiting_review')
        with self.assertRaises(Work4ceError): self.proposal()
        review=self.result['review']
        with self.assertRaises(Work4ceError):
            self.service.decide_review(owner(permissions=PERMISSIONS|ADMIN_PERMISSIONS),self.identity,review['review_id'],'approved')
        self.accept()
        self.assertEqual(self.store.get(TENANT,self.identity)['status'],'completed')
        self.assertEqual(self.events.calls,1)

    async def test_review_rejection_is_terminal_and_cannot_authorize_response(self):
        review=self.result['review']
        self.service.decide_review(reviewer(),self.identity,review['review_id'],'rejected','Needs more evidence')
        self.assertEqual(self.store.get(TENANT,self.identity)['status'],'review_rejected')
        with self.assertRaises(Work4ceError): self.proposal()
        with self.assertRaises(Work4ceError):
            self.service.decide_review(reviewer(),self.identity,review['review_id'],'approved')

    async def test_missing_mismatched_reused_approval_never_authorizes_simulation(self):
        self.accept()
        proposal=self.proposal()
        with self.assertRaisesRegex(Work4ceError,'approval_required'):
            self.service.simulate(owner(),proposal['id'],str(uuid4()))
        approved=self.service.decide_response(reviewer(),proposal['id'],'approved')
        with self.assertRaisesRegex(Work4ceError,'approval_mismatch'):
            self.service.simulate(owner(),proposal['id'],str(uuid4()))
        result=self.service.simulate(owner(),proposal['id'],approved['approval_id'])
        self.assertEqual(result['state'],'consumed')
        self.assertTrue(result['simulation_result']['dry_run'])
        self.assertFalse(result['simulation_result']['performed'])
        with self.assertRaisesRegex(Work4ceError,'approval_reused'):
            self.service.simulate(owner(),proposal['id'],approved['approval_id'])
        self.assertEqual(self.events.calls,1)

    async def test_expired_and_revoked_approval_denied(self):
        approved=self.approved()
        with self.store.engine.begin() as connection:
            connection.execute(update(response_approvals).where(response_approvals.c.id==approved['id']).values(expires_at=time.time()-1))
        with self.assertRaisesRegex(Work4ceError,'approval_expired'):
            self.service.simulate(owner(),approved['id'],approved['approval_id'])
        second=self.proposal()
        second=self.service.decide_response(reviewer(),second['id'],'approved')
        self.service.revoke(owner(),second['id'])
        with self.assertRaises(Work4ceError):
            self.service.simulate(owner(),second['id'],second['approval_id'])
        self.assertEqual(self.events.calls,1)

    async def test_current_permissions_and_source_grants_rechecked(self):
        approved=self.approved()
        for context in (owner(permissions=PERMISSIONS-{'responses:simulate'}),owner(allowed_connectors=frozenset()),
                        owner(synthetic=False),owner(tenant_id='foreign')):
            with self.subTest(context=context),self.assertRaises(Work4ceError):
                self.service.simulate(context,approved['id'],approved['approval_id'])
        self.tools.disable(owner(permissions=PERMISSIONS|ADMIN_PERMISSIONS),'demo-rest')
        with self.assertRaises(Work4ceError):
            self.service.simulate(owner(),approved['id'],approved['approval_id'])
        self.assertEqual(self.store.get_response(TENANT,approved['id'])['state'],'approved')

    async def test_approval_cannot_cross_requester_tenant_or_action(self):
        approved=self.approved()
        for context in (owner(subject='other'),owner(tenant_id='other')):
            with self.subTest(context=context),self.assertRaises(Work4ceError):
                self.service.simulate(context,approved['id'],approved['approval_id'])
        for action,target,params in (('endpoint.delete','demo-host-1',{'duration_minutes':15}),
                                    ('endpoint.isolate','production-host',{'duration_minutes':15}),
                                    ('endpoint.isolate','demo-host-2',{'duration_minutes':15}),
                                    ('endpoint.isolate','demo-host-1',{'duration_minutes':True})):
            with self.subTest(action=action,target=target),self.assertRaises(Work4ceError):
                self.service.propose(owner(),self.identity,action,target,params)
        with self.assertRaises(Work4ceError):
            self.service.decide_response(owner(permissions=PERMISSIONS|ADMIN_PERMISSIONS),self.proposal()['id'],'approved')
        self.assertEqual(self.events.calls,1)

    async def test_queues_and_records_are_scoped(self):
        approved=self.approved()
        self.assertEqual(len(self.service.list_reviews(reviewer())),1)
        with self.assertRaises(Work4ceError): self.service.list_reviews(owner())
        with self.assertRaises(Work4ceError):
            self.service.request_review(owner(permissions=PERMISSIONS-{'investigations:run'}),self.identity)
        self.assertEqual(self.service.list_responses(owner())[0]['id'],approved['id'])
        self.assertEqual(self.service.list_responses(owner(subject='other')),[])
        self.assertEqual(self.service.list_responses(reviewer())[0]['id'],approved['id'])
        with self.assertRaises(Work4ceError): self.service.get_review(owner(subject='other'),self.identity)
        with self.assertRaises(Work4ceError): self.service.get_response(owner(subject='other'),approved['id'])

    async def test_pending_review_survives_store_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'review.db')
            store=Store(path)
            events=Events()
            tools=await tools_for(store,events)
            result=await Investigator(tools,store,require_review=True).investigate(owner(),'PowerShell')
            store.close()
            store=Store(path)
            try:
                tools=await tools_for(store,events)
                service=ReviewService(store,tools)
                saved=store.get(TENANT,result['id'])
                self.assertEqual(saved,result)
                service.decide_review(reviewer(),result['id'],saved['review']['review_id'],'approved')
                self.assertEqual(store.get(TENANT,result['id'])['status'],'completed')
                self.assertEqual(events.calls,1)
            finally: store.close()


class ReviewAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.events=Events()
        self.tools=await tools_for(self.store,self.events)
        self.app=create_app(Settings('x'*40,'y'*40,require_human_review=True),self.tools)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')
        self.auth={'Authorization':'Bearer '+'x'*40}
        self.admin={'Authorization':'Bearer '+'y'*40}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    async def test_full_http_review_approval_and_single_use_dry_run(self):
        response=await self.client.post('/investigations',json={'query':'PowerShell'},headers=self.auth)
        self.assertEqual(response.status_code,201,response.text)
        case=response.json()
        self.assertEqual(case['status'],'awaiting_review')
        identity=case['id']
        state=(await self.client.get('/investigations/'+identity+'/state',headers=self.auth)).json()
        self.assertEqual(state['execution_status'],'completed')
        self.assertEqual(state['status'],'awaiting_review')
        self.assertEqual((await self.client.get('/reviews',headers=self.auth)).status_code,403)
        self.assertEqual(len((await self.client.get('/reviews',headers=self.admin)).json()),1)
        decision={'review_id':case['review']['review_id'],'decision':'approved','comment':'Evidence checked'}
        self.assertEqual((await self.client.post('/investigations/'+identity+'/review/decision',json=decision,headers=self.auth)).status_code,403)
        accepted=await self.client.post('/investigations/'+identity+'/review/decision',json=decision,headers=self.admin)
        self.assertEqual(accepted.status_code,200,accepted.text)
        proposal=await self.client.post('/responses',json={'investigation_id':identity,'action':'endpoint.isolate',
            'target':'demo-host-1','parameters':{'duration_minutes':15}},headers=self.auth)
        self.assertEqual(proposal.status_code,201,proposal.text)
        response_id=proposal.json()['id']
        approved=await self.client.post('/responses/'+response_id+'/decision',json={'decision':'approved'},headers=self.admin)
        self.assertEqual(approved.status_code,200,approved.text)
        self.assertEqual((await self.client.post('/responses/'+response_id+'/simulate',json={},headers=self.auth)).status_code,422)
        self.assertEqual((await self.client.post('/responses/'+response_id+'/simulate',json={'approval_id':str(uuid4())},headers=self.auth)).status_code,403)
        body={'approval_id':approved.json()['approval_id']}
        simulation=await self.client.post('/responses/'+response_id+'/simulate',json=body,headers=self.auth)
        self.assertEqual(simulation.status_code,200,simulation.text)
        self.assertFalse(simulation.json()['simulation_result']['performed'])
        self.assertEqual((await self.client.post('/responses/'+response_id+'/simulate',json=body,headers=self.auth)).status_code,409)
        self.assertEqual(self.events.calls,1)

    async def test_body_cannot_disable_review_or_spoof_actor(self):
        for body in ({'query':'PowerShell','require_human_review':False},
                     {'query':'PowerShell','reviewer':'admin'}):
            result=await self.client.post('/investigations',json=body,headers=self.auth)
            self.assertEqual(result.status_code,422)
        self.assertEqual((await self.client.get('/reviews')).status_code,401)
        self.assertEqual((await self.client.post('/responses',json={},headers=self.auth)).status_code,422)
        self.assertEqual(self.events.calls,0)

    async def test_manual_review_gates_a_previously_completed_report(self):
        app=create_app(Settings('x'*40,'y'*40),self.tools)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            result=await client.post('/investigations',json={'query':'PowerShell'},headers=self.auth)
            self.assertEqual(result.json()['status'],'completed')
            identity=result.json()['id']
            requested=await client.post('/investigations/'+identity+'/review',headers=self.auth)
            self.assertEqual(requested.status_code,200,requested.text)
            state=(await client.get('/investigations/'+identity+'/state',headers=self.auth)).json()
            self.assertEqual(state['status'],'awaiting_review')
            self.assertEqual(state['execution_status'],'completed')
            replay=await client.post('/investigations/'+identity+'/resume',headers=self.auth)
            self.assertEqual(replay.json()['status'],'awaiting_review')
            self.assertEqual(self.events.calls,1)

    def test_review_policy_setting_requires_explicit_boolean(self):
        variables={'WORK4CE_DEMO_TOKEN':'x'*40,'WORK4CE_ADMIN_TOKEN':'y'*40,
                   'WORK4CE_REQUIRE_HUMAN_REVIEW':'true'}
        with patch.dict('os.environ',variables,clear=True):
            self.assertTrue(Settings.from_environment().require_human_review)
        with patch.dict('os.environ',{**variables,'WORK4CE_REQUIRE_HUMAN_REVIEW':'invalid'},clear=True),self.assertRaises(ValueError):
            Settings.from_environment()
        with self.assertRaises(ValueError):
            Settings('x'*40,'y'*40,require_human_review='false')

    async def test_tenant_report_read_does_not_expose_private_review_metadata(self):
        created=await self.client.post('/investigations',json={'query':'PowerShell'},headers=self.auth)
        case=created.json()
        identity=case['id']
        decision={'review_id':case['review']['review_id'],'decision':'approved','comment':'private-review-comment'}
        accepted=await self.client.post('/investigations/'+identity+'/review/decision',json=decision,headers=self.admin)
        self.assertEqual(accepted.status_code,200,accepted.text)
        route=next(route for route in self.app.routes if route.path=='/investigations/{identity}')
        auth_dependency=route.dependant.dependencies[0].call
        self.app.dependency_overrides[auth_dependency]=lambda: owner(subject='another-analyst')
        response=await self.client.get('/investigations/'+identity,headers=self.auth)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('review',response.json())
        self.assertNotIn('private-review-comment',response.text)
        denied=await self.client.get('/investigations/'+identity+'/review',headers=self.auth)
        self.assertEqual(denied.status_code,404)
        self.app.dependency_overrides.clear()
