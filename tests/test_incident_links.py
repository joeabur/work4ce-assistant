"""Combined incidents require every source's current case scope."""
import unittest

import httpx

from work4ce_assistant.api import create_app,Settings,TENANT
from work4ce_assistant.storage import Store
from test_reviews import Events,tools_for


class IncidentLinkAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.gateway=await tools_for(self.store,Events())
        self.app=create_app(Settings('a'*40,'b'*40,require_human_review=True),self.gateway)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')
        self.auth={'Authorization':'Bearer '+'a'*40}
        self.admin={'Authorization':'Bearer '+'b'*40}
        response=await self.client.post('/investigations',headers=self.auth,json={'query':'PowerShell'})
        self.assertEqual(response.status_code,201,response.text)
        self.original=response.json()
        self.primary=self.original['id']
        response=await self.client.post('/incidents',headers=self.auth,json={
            'investigation_id':self.primary,'title':'Related synthetic investigations','severity':'high'})
        self.assertEqual(response.status_code,201,response.text)
        self.incident=response.json()
        self.base='/incidents/'+self.incident['id']

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    def source(self,owner='demo-analyst',tenant=TENANT):
        identity=self.store.begin(tenant,owner)
        # A duplicated evidence ID tests explicit source namespaces.
        self.store.finish(tenant,owner,identity,{'synthetic':True,'query':'Related synthetic source',
            'evidence':[{'evidence_id':self.original['report']['evidence'][0]['evidence_id'],
                'content':{'summary':'A different source with the same local evidence ID.'}}]},'completed')
        return identity

    async def link(self,source,*,revision=1,headers=None,**extra):
        return await self.client.post(self.base+'/investigations',headers=headers or self.auth,
            json={'expected_revision':revision,'investigation_id':source,
                  'comment':'Related synthetic process context.',**extra})

    async def test_linked_sources_map_to_one_incident_and_preserve_original_reports(self):
        secondary=self.source()
        before=self.store.get(TENANT,secondary)
        linked=await self.link(secondary)
        self.assertEqual(linked.status_code,200,linked.text)
        self.assertEqual(linked.json()['revision'],2)
        self.assertEqual(linked.json()['investigation_id'],self.primary)
        for source in (self.primary,secondary):
            response=await self.client.get('/investigations/'+source+'/incident',headers=self.auth)
            self.assertEqual(response.json()['id'],self.incident['id'])
        sources=(await self.client.get(self.base+'/investigations',headers=self.auth)).json()
        self.assertEqual([item['investigation_id'] for item in sources],[self.primary,secondary])
        self.assertTrue(sources[0]['primary'])
        self.assertFalse(sources[1]['primary'])
        for source in sources:
            self.assertEqual(set(source),{'investigation_id','primary','creator','assignee','query','linked_by','linked_at','evidence','escalation_state'})
            self.assertFalse({'review','comment','report','checkpoint','approval_id'} & source.keys())
        duplicate=await self.client.post('/incidents',headers=self.auth,json={
            'investigation_id':secondary,'title':'Must not duplicate a linked source','severity':'low'})
        self.assertEqual(duplicate.status_code,409)
        self.assertEqual(duplicate.json(),{'error':'incident_exists'})
        self.assertEqual(self.store.get(TENANT,self.primary),self.original)
        self.assertEqual(self.store.get(TENANT,secondary),before)

    async def test_linking_never_grants_access_and_reassignment_revokes_combined_access(self):
        secondary=self.source('other-creator')
        self.assertEqual((await self.link(secondary)).status_code,404)
        linked=await self.link(secondary,headers=self.admin)
        self.assertEqual(linked.status_code,200,linked.text)
        for path in (self.base,self.base+'/activity',self.base+'/investigations',
                     '/investigations/'+self.primary+'/incident'):
            self.assertEqual((await self.client.get(path,headers=self.auth)).status_code,404)
        self.assertEqual((await self.client.get('/incidents',headers=self.auth)).json(),[])
        denied=await self.client.post(self.base+'/notes',headers=self.auth,
            json={'expected_revision':2,'body':'Original authorship cannot bypass another case scope.'})
        self.assertEqual(denied.status_code,404)
        path='/investigations/'+secondary+'/case/assignment'
        granted=await self.client.post(path,headers=self.admin,json={'expected_revision':0,'assignee':'demo-analyst'})
        self.assertEqual(granted.status_code,200,granted.text)
        self.assertEqual((await self.client.get(self.base,headers=self.auth)).status_code,200)
        self.assertEqual(len((await self.client.get('/incidents',headers=self.auth)).json()),1)
        await self.client.post(path,headers=self.admin,json={'expected_revision':1,'assignee':None})
        self.assertEqual((await self.client.get(self.base+'/activity',headers=self.auth)).status_code,404)
        self.assertEqual((await self.client.get('/incidents',headers=self.auth)).json(),[])

    async def test_evidence_references_are_namespaced_and_legacy_primary_notes_still_work(self):
        secondary=self.source()
        self.assertEqual((await self.link(secondary)).status_code,200)
        evidence=self.original['report']['evidence'][0]['evidence_id']
        references=[{'investigation_id':source,'evidence_id':evidence} for source in (self.primary,secondary)]
        note=await self.client.post(self.base+'/notes',headers=self.auth,
            json={'expected_revision':2,'body':'Different investigations, same local evidence ID.','references':references})
        self.assertEqual(note.status_code,200,note.text)
        legacy=await self.client.post(self.base+'/notes',headers=self.auth,
            json={'expected_revision':3,'body':'Legacy primary reference.','evidence_ids':[evidence]})
        self.assertEqual(legacy.status_code,200,legacy.text)
        activity=(await self.client.get(self.base+'/activity',headers=self.auth)).json()
        self.assertEqual(activity[1]['kind'],'linked')
        self.assertEqual(activity[1]['linked_investigation_id'],secondary)
        self.assertEqual(activity[2]['references'],references)
        self.assertEqual(activity[2]['evidence_ids'],[evidence])
        self.assertEqual(activity[3]['references'],references[:1])
        unknown=self.source()
        for refs in ([{'investigation_id':unknown,'evidence_id':evidence}],
                     [{'investigation_id':secondary,'evidence_id':'forged'}],references*2):
            response=await self.client.post(self.base+'/notes',headers=self.auth,
                json={'expected_revision':4,'body':'Invalid reference.','references':refs})
            self.assertEqual(response.status_code,422,response.text)
        response=await self.client.post(self.base+'/notes',headers=self.auth,
            json={'expected_revision':4,'body':'Ambiguous input.','evidence_ids':[evidence],'references':references})
        self.assertEqual(response.status_code,422)

    async def test_pending_secondary_escalation_blocks_resolution_and_stale_links_conflict(self):
        secondary=self.source()
        self.assertEqual((await self.link(secondary)).status_code,200)
        stale=await self.link(self.source(),revision=1)
        self.assertEqual(stale.status_code,409)
        self.assertEqual(stale.json(),{'error':'incident_revision_conflict'})
        path='/investigations/'+secondary+'/case'
        await self.client.post(path+'/escalation',headers=self.auth,
            json={'expected_revision':0,'reason':'Related case needs management attention.'})
        response=await self.client.post(self.base+'/status',headers=self.admin,
            json={'expected_revision':2,'status':'resolved','comment':'Cannot ignore the related escalation.'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json(),{'error':'incident_escalation_pending'})
        await self.client.post(path+'/acknowledge',headers=self.admin,json={'expected_revision':1})
        resolved=await self.client.post(self.base+'/status',headers=self.auth,
            json={'expected_revision':2,'status':'resolved','comment':'Both source cases reviewed.'})
        self.assertEqual(resolved.status_code,200,resolved.text)
        blocked=await self.link(self.source(),revision=3)
        self.assertEqual(blocked.status_code,409)
        self.assertEqual(blocked.json(),{'error':'incident_not_active'})

    async def test_link_payloads_are_strict_and_foreign_sources_are_hidden(self):
        secondary=self.source()
        for extra in ({'manage':True},{'actor':'demo-admin'},{'tenant':'foreign'},{'report_hash':'forged'},
                      {'comment':' '},{'comment':'x'*2001},{'expected_revision':True}):
            response=await self.link(secondary,**extra)
            self.assertEqual(response.status_code,422,response.text)
        foreign=self.source(tenant='foreign')
        self.assertEqual((await self.link(foreign,headers=self.admin)).status_code,404)
        self.assertEqual((await self.client.get(self.base+'/investigations')).status_code,401)
        self.assertEqual((await self.client.get(self.base,headers=self.auth)).json()['revision'],1)


if __name__=='__main__': unittest.main()
