"""Case policy and authenticated assignment never transfer workflow authority."""
from dataclasses import replace
import unittest

import httpx

from work4ce_assistant.api import (create_app,Settings,TENANT,PERMISSIONS,ADMIN_PERMISSIONS,
                                   REVIEWER_PERMISSIONS,CONNECTORS)
from work4ce_assistant.cases import CaseService
from work4ce_assistant.contracts import ExecutionContext,Work4ceError
from work4ce_assistant.storage import Store
from test_reviews import Events,tools_for


def actor(subject='alice',permissions=PERMISSIONS,**changes):
    return replace(ExecutionContext(TENANT,subject,permissions,CONNECTORS,True),**changes)


class CasePolicyTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:')
        self.service=CaseService(self.store,TENANT,frozenset({'alice','bob','manager'}))
        self.identity=self.store.begin(TENANT,'alice')
        self.manager=actor('manager',PERMISSIONS|ADMIN_PERMISSIONS)

    def tearDown(self): self.store.close()

    def test_directory_is_trusted_and_only_eligible_subjects_can_be_assigned(self):
        self.assertEqual(self.service.directory(actor()),[{'subject':'alice'},{'subject':'bob'},{'subject':'manager'}])
        for invalid in ('reviewer','external-subject',[],True):
            with self.assertRaisesRegex(Work4ceError,'invalid_case_assignee'):
                self.service.assign(actor(),self.identity,0,invalid)
        result=self.service.assign(actor(),self.identity,0,'bob')
        self.assertEqual(result['assignee'],'bob')

    def test_reviewer_reads_without_mutation_or_directory_grants(self):
        reviewer=actor('reviewer',REVIEWER_PERMISSIONS)
        self.assertEqual(self.service.get(reviewer,self.identity)['creator'],'alice')
        for operation in (lambda:self.service.assign(reviewer,self.identity,0,'bob'),
                          lambda:self.service.escalate(reviewer,self.identity,0,'Needs attention'),
                          lambda:self.service.acknowledge(reviewer,self.identity,0),
                          lambda:self.service.directory(reviewer)):
            with self.assertRaisesRegex(Work4ceError,'permission_denied'):
                operation()

    def test_synthetic_tenant_and_current_grants_are_required(self):
        for context in (actor(synthetic=False),actor(tenant_id='foreign'),
                        actor(permissions=PERMISSIONS-{'cases:read'}),
                        actor(permissions=PERMISSIONS-{'investigations:read'})):
            with self.assertRaisesRegex(Work4ceError,'permission_denied'):
                self.service.get(context,self.identity)
        with self.assertRaisesRegex(Work4ceError,'case_not_found'):
            self.service.get(actor('bob'),self.identity)
        self.service.assign(actor(),self.identity,0,'bob')
        with self.assertRaisesRegex(Work4ceError,'permission_denied'):
            self.service.escalate(actor('bob',PERMISSIONS-{'cases:coordinate'}),self.identity,1,'Needs attention')

    def test_assignee_can_escalate_but_only_manager_can_acknowledge(self):
        self.service.assign(actor(),self.identity,0,'bob')
        requested=self.service.escalate(actor('bob'),self.identity,1,'  Inspect the synthetic evidence.  ')
        self.assertEqual(requested['escalation_reason'],'Inspect the synthetic evidence.')
        self.assertEqual(requested['escalated_by'],'bob')
        with self.assertRaisesRegex(Work4ceError,'permission_denied'):
            self.service.acknowledge(actor('bob'),self.identity,2)
        acknowledged=self.service.acknowledge(self.manager,self.identity,2)
        self.assertEqual(acknowledged['acknowledged_by'],'manager')
        self.assertEqual(acknowledged['creator'],'alice')
        again=self.service.escalate(actor(),self.identity,3,'Additional synthetic context.')
        self.assertEqual(again['escalation_state'],'requested')
        self.assertIsNone(again['acknowledged_by'])


class CaseAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.tools=await tools_for(self.store,Events())
        self.app=create_app(Settings('a'*40,'b'*40,require_human_review=True),self.tools)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')
        self.auth={'Authorization':'Bearer '+'a'*40}
        self.admin={'Authorization':'Bearer '+'b'*40}
        self.identity=self.store.begin(TENANT,'demo-analyst')
        self.base='/investigations/'+self.identity+'/case'

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    async def test_authenticated_default_and_directory_have_no_embedded_credential(self):
        for path in ('/case-assignees','/cases',self.base):
            self.assertEqual((await self.client.get(path)).status_code,401)
            response=await self.client.get(path,headers=self.auth)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertNotIn('a'*40,response.text)
        self.assertEqual((await self.client.get('/cases',headers=self.auth)).json(),[])
        self.assertEqual((await self.client.get(self.base,headers=self.auth)).json()['revision'],0)
        self.assertEqual((await self.client.get('/case-assignees',headers=self.auth)).json(),
                         [{'subject':'demo-admin'},{'subject':'demo-analyst'}])

    async def test_assignment_escalation_acknowledgment_and_stale_revision(self):
        response=await self.client.post(self.base+'/assignment',headers=self.auth,
            json={'expected_revision':0,'assignee':'demo-admin'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['revision'],1)
        stale=await self.client.post(self.base+'/assignment',headers=self.auth,
            json={'expected_revision':0,'assignee':None})
        self.assertEqual(stale.status_code,409)
        self.assertEqual(stale.json(),{'error':'case_revision_conflict'})
        result=await self.client.post(self.base+'/escalation',headers=self.auth,
            json={'expected_revision':1,'reason':'Inspect synthetic process evidence.'})
        self.assertEqual(result.status_code,200,result.text)
        denied=await self.client.post(self.base+'/acknowledge',headers=self.auth,json={'expected_revision':2})
        self.assertEqual(denied.status_code,403)
        accepted=await self.client.post(self.base+'/acknowledge',headers=self.admin,json={'expected_revision':2})
        self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(accepted.json()['escalation_state'],'acknowledged')
        queue=(await self.client.get('/cases',headers=self.admin)).json()
        self.assertEqual([item['investigation_id'] for item in queue],[self.identity])

    async def test_body_cannot_forge_actor_tenant_permissions_or_revision(self):
        valid={'expected_revision':0,'assignee':'demo-admin'}
        for key,value in (('actor','demo-admin'),('tenant','foreign'),('manage',True),('permissions',['*'])):
            response=await self.client.post(self.base+'/assignment',headers=self.auth,json={**valid,key:value})
            self.assertEqual(response.status_code,422,response.text)
        for revision in (True,-1,1.5,'0',2_147_483_647):
            response=await self.client.post(self.base+'/assignment',headers=self.auth,
                json={**valid,'expected_revision':revision})
            self.assertEqual(response.status_code,422,response.text)
        for assignee in ('unknown','',True):
            response=await self.client.post(self.base+'/assignment',headers=self.auth,json={**valid,'assignee':assignee})
            self.assertEqual(response.status_code,422,response.text)
        for reason in ('','   ','x'*1001,False):
            response=await self.client.post(self.base+'/escalation',headers=self.auth,
                json={'expected_revision':0,'reason':reason})
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual((await self.client.get(self.base,headers=self.auth)).json()['revision'],0)

    async def test_unrelated_actor_and_foreign_tenant_cannot_read_or_mutate_coordination(self):
        other=self.store.begin(TENANT,'another-analyst')
        foreign=self.store.begin('foreign','demo-analyst')
        for identity in (other,foreign):
            path='/investigations/'+identity+'/case'
            self.assertEqual((await self.client.get(path,headers=self.auth)).status_code,404)
            self.assertEqual((await self.client.post(path+'/assignment',headers=self.auth,
                json={'expected_revision':0,'assignee':'demo-admin'})).status_code,404)
        # Tenant-wide report-read does not publish coordination notes.
        self.store.finish(TENANT,'another-analyst',other,{'synthetic':True,'query':'private coordination'},'completed')
        response=await self.client.get('/investigations/'+other,headers=self.auth)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('case',response.json())
        self.assertNotIn('coordination',response.json())

    async def test_assignment_preserves_workflow_and_review_requester_authority(self):
        response=await self.client.post('/investigations',headers=self.auth,json={'query':'PowerShell'})
        self.assertEqual(response.status_code,201,response.text)
        original=response.json()
        identity=original['id']
        base='/investigations/'+identity
        assigned=await self.client.post(base+'/case/assignment',headers=self.auth,
            json={'expected_revision':0,'assignee':'demo-admin'})
        self.assertEqual(assigned.status_code,200,assigned.text)
        await self.client.post(base+'/case/escalation',headers=self.admin,
            json={'expected_revision':1,'reason':'Manager coordination.'})
        await self.client.post(base+'/case/acknowledge',headers=self.admin,json={'expected_revision':2})
        current=(await self.client.get(base,headers=self.auth)).json()
        self.assertEqual(current,original)
        self.assertEqual(current['review']['requester'],'demo-analyst')
        self.assertEqual(current['review']['state'],'pending')
        for operation in ('resume','cancel'):
            self.assertEqual((await self.client.post(base+'/'+operation,headers=self.admin)).status_code,404)
        proposal=await self.client.post('/responses',headers=self.admin,json={'investigation_id':identity,
            'action':'endpoint.isolate','target':'demo-host-1','parameters':{'duration_minutes':5}})
        self.assertEqual(proposal.status_code,404,proposal.text)

    async def test_case_limit_validation(self):
        for limit in ('0','101','invalid'):
            self.assertEqual((await self.client.get('/cases',params={'limit':limit},headers=self.auth)).status_code,422)


if __name__=='__main__': unittest.main()
