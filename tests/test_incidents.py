"""Authenticated incident lifecycle stays separate from report/response authority."""
import unittest

import httpx

from work4ce_assistant.api import create_app,Settings,TENANT
from work4ce_assistant.storage import Store
from test_reviews import Events,tools_for


class IncidentAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.gateway=await tools_for(self.store,Events())
        self.app=create_app(Settings('a'*40,'b'*40,require_human_review=True),self.gateway)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')
        self.auth={'Authorization':'Bearer '+'a'*40}
        self.admin={'Authorization':'Bearer '+'b'*40}
        result=await self.client.post('/investigations',headers=self.auth,json={'query':'PowerShell'})
        self.assertEqual(result.status_code,201,result.text)
        self.source=result.json()
        self.investigation_id=self.source['id']

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    async def create(self,**changes):
        return await self.client.post('/incidents',headers=self.auth,json={
            'investigation_id':self.investigation_id,'title':'Synthetic endpoint investigation',
            'description':'Human triage context.','severity':'high',**changes})

    async def test_creation_links_source_and_duplicate_retry_cannot_create_another(self):
        absent=await self.client.get('/investigations/'+self.investigation_id+'/incident',headers=self.auth)
        self.assertEqual(absent.status_code,404)
        self.assertEqual((await self.client.get('/incidents',headers=self.auth)).json(),[])
        response=await self.create()
        self.assertEqual(response.status_code,201,response.text)
        item=response.json()
        self.assertEqual(item['investigation_id'],self.investigation_id)
        self.assertEqual(item['status'],'open')
        self.assertEqual(item['revision'],1)
        self.assertEqual(item['creator'],'demo-analyst')
        self.assertEqual(item['created_by'],'demo-analyst')
        duplicate=await self.create()
        self.assertEqual(duplicate.status_code,409)
        self.assertEqual(duplicate.json(),{'error':'incident_exists'})
        linked=await self.client.get('/investigations/'+self.investigation_id+'/incident',headers=self.auth)
        self.assertEqual(linked.json(),item)
        self.assertEqual(len((await self.client.get('/incidents',headers=self.auth)).json()),1)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertNotIn('a'*40,response.text)

    async def test_notes_resolution_closure_and_reopen_retain_author_history(self):
        item=(await self.create()).json()
        base='/incidents/'+item['id']
        response=await self.client.post(base+'/status',headers=self.auth,
            json={'expected_revision':1,'status':'in_progress'})
        self.assertEqual(response.status_code,200,response.text)
        evidence=self.source['report']['evidence'][0]['evidence_id']
        note=await self.client.post(base+'/notes',headers=self.auth,json={
            'expected_revision':2,'body':'Observed synthetic process activity.','evidence_ids':[evidence]})
        self.assertEqual(note.status_code,200,note.text)
        resolved=await self.client.post(base+'/status',headers=self.auth,json={
            'expected_revision':3,'status':'resolved','comment':'Synthetic exercise reviewed; document the remaining uncertainty.'})
        self.assertEqual(resolved.status_code,200,resolved.text)
        self.assertEqual(resolved.json()['resolved_by'],'demo-analyst')
        denied=await self.client.post(base+'/status',headers=self.auth,json={
            'expected_revision':4,'status':'closed','comment':'Unauthorized manager closure.'})
        self.assertEqual(denied.status_code,403)
        closed=await self.client.post(base+'/status',headers=self.admin,json={
            'expected_revision':4,'status':'closed','comment':'Manager disposition recorded.'})
        self.assertEqual(closed.status_code,200,closed.text)
        self.assertEqual(closed.json()['closed_by'],'demo-admin')
        blocked=await self.client.post(base+'/notes',headers=self.auth,
            json={'expected_revision':5,'body':'Closed case cannot be edited.'})
        self.assertEqual(blocked.status_code,409)
        denied=await self.client.post(base+'/status',headers=self.auth,
            json={'expected_revision':5,'status':'open','comment':'Non-manager reopen.'})
        self.assertEqual(denied.status_code,403)
        reopened=await self.client.post(base+'/status',headers=self.admin,
            json={'expected_revision':5,'status':'open','comment':'Reopen for additional synthetic context.'})
        self.assertEqual(reopened.status_code,200,reopened.text)
        self.assertIsNone(reopened.json()['resolution_note'])
        self.assertIsNone(reopened.json()['closed_by'])
        activity=(await self.client.get(base+'/activity',headers=self.auth)).json()
        self.assertEqual([entry['sequence'] for entry in activity],[1,2,3,4,5,6])
        self.assertEqual(activity[2]['kind'],'note')
        self.assertEqual(activity[2]['evidence_ids'],[evidence])
        self.assertEqual(activity[4]['actor'],'demo-admin')
        self.assertIn('remaining uncertainty',activity[3]['body'])
        self.assertEqual((await self.client.get('/investigations/'+self.investigation_id,headers=self.auth)).json(),self.source)
        self.assertEqual(self.source['review']['state'],'pending')

    async def test_pending_escalation_and_stale_revisions_fail_closed(self):
        item=(await self.create()).json()
        base='/incidents/'+item['id']
        path='/investigations/'+self.investigation_id+'/case'
        await self.client.post(path+'/escalation',headers=self.auth,
            json={'expected_revision':0,'reason':'Management attention is still required.'})
        blocked=await self.client.post(base+'/status',headers=self.admin,
            json={'expected_revision':1,'status':'resolved','comment':'Cannot bypass pending escalation.'})
        self.assertEqual(blocked.status_code,409)
        self.assertEqual(blocked.json(),{'error':'incident_escalation_pending'})
        await self.client.post(path+'/acknowledge',headers=self.admin,json={'expected_revision':1})
        self.assertEqual((await self.client.post(base+'/notes',headers=self.auth,
            json={'expected_revision':1,'body':'A new note changes the incident revision.'})).status_code,200)
        stale=await self.client.post(base+'/status',headers=self.auth,
            json={'expected_revision':1,'status':'resolved','comment':'Stale disposition.'})
        self.assertEqual(stale.status_code,409)
        self.assertEqual(stale.json(),{'error':'incident_revision_conflict'})

    async def test_request_bodies_cannot_forge_actors_or_links_or_approval_grants(self):
        for field,value in (('creator','demo-admin'),('tenant','foreign'),('manage',True),
                            ('report_hash','forged'),('approval_id','forged')):
            response=await self.create(**{field:value})
            self.assertEqual(response.status_code,422,response.text)
        for title in ('',' ','x'*201):
            self.assertEqual((await self.create(title=title)).status_code,422)
        for severity in ('benign','admin',True):
            self.assertEqual((await self.create(severity=severity)).status_code,422)
        item=(await self.create()).json()
        for revision in (0,True,'1',1.5,201):
            response=await self.client.post('/incidents/'+item['id']+'/notes',headers=self.auth,
                json={'expected_revision':revision,'body':'Invalid revision.'})
            self.assertEqual(response.status_code,422,response.text)
        for evidence in (['forged'],['x']*11,[True]):
            response=await self.client.post('/incidents/'+item['id']+'/notes',headers=self.auth,
                json={'expected_revision':1,'body':'Invalid evidence reference.','evidence_ids':evidence})
            self.assertEqual(response.status_code,422,response.text)
        for comment in ('',' ','x'*2001):
            response=await self.client.post('/incidents/'+item['id']+'/status',headers=self.auth,
                json={'expected_revision':1,'status':'resolved','comment':comment})
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual((await self.client.get('/incidents/'+item['id'],headers=self.auth)).json()['revision'],1)

    async def test_unrelated_analysts_cannot_access_incidents_or_activity(self):
        other=self.store.begin(TENANT,'unrelated-analyst')
        self.store.finish(TENANT,'unrelated-analyst',other,{'synthetic':True,'evidence':[]},'completed')
        made=await self.client.post('/incidents',headers=self.admin,json={
            'investigation_id':other,'title':'Other coordinator case','description':'Private context.','severity':'low'})
        self.assertEqual(made.status_code,201,made.text)
        identity=made.json()['id']
        for path in ('/incidents/'+identity,'/incidents/'+identity+'/activity','/investigations/'+other+'/incident'):
            self.assertEqual((await self.client.get(path,headers=self.auth)).status_code,404)
            self.assertEqual((await self.client.get(path)).status_code,401)
        self.assertEqual((await self.client.post('/incidents/'+identity+'/notes',headers=self.auth,
            json={'expected_revision':1,'body':'Not in my scope.'})).status_code,404)
        self.assertEqual((await self.client.get('/incidents',headers=self.auth)).json(),[])
        self.assertNotIn('incident',(await self.client.get('/investigations/'+other,headers=self.auth)).json())

    async def test_incomplete_source_and_invalid_queue_limit_are_rejected(self):
        queued=self.store.begin(TENANT,'demo-analyst')
        response=await self.create(investigation_id=queued)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json(),{'error':'incident_source_incomplete'})
        self.assertEqual((await self.client.get('/investigations/'+queued+'/incident',headers=self.auth)).status_code,404)
        for limit in ('0','101','invalid'):
            self.assertEqual((await self.client.get('/incidents',headers=self.auth,params={'limit':limit})).status_code,422)


if __name__=='__main__': unittest.main()
