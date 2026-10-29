"""Operational cursor endpoints preserve legacy APIs and current authorization."""
import unittest

import httpx

from work4ce_assistant.api import create_app,Settings,TENANT,PERMISSIONS,CONNECTORS
from work4ce_assistant.contracts import ExecutionContext
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.incident_storage import IncidentRepository
from work4ce_assistant.storage import Store


class QueuePageAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.repository=IncidentRepository(self.store)
        self.incidents=[]
        for index in range(3):
            source=self.store.begin(TENANT,'demo-analyst')
            self.store.finish(TENANT,'demo-analyst',source,{'synthetic':True,'query':'Queue fixture '+str(index),'evidence':[]},'completed')
            self.store.mutate_case(TENANT,'demo-analyst',source,0,'assign',assignee='demo-analyst')
            self.incidents.append(self.repository.create(TENANT,'demo-analyst',source,'Queue '+str(index),'Human context','low'))
        self.app=create_app(Settings('a'*40,'b'*40),Gateway(self.store))
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')
        self.auth={'Authorization':'Bearer '+'a'*40}
        self.admin={'Authorization':'Bearer '+'b'*40}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    async def test_literal_page_routes_authenticate_and_preserve_legacy_arrays(self):
        for path,key in (('/cases','investigation_id'),('/incidents','id')):
            self.assertEqual((await self.client.get(path+'/history')).status_code,401)
            legacy=await self.client.get(path,headers=self.auth)
            self.assertIsInstance(legacy.json(),list)
            page=await self.client.get(path+'/history',headers=self.auth,params={'limit':1})
            self.assertEqual(page.status_code,200,page.text)
            self.assertEqual(set(page.json()),{'items','next_cursor'})
            self.assertIsInstance(page.json()['next_cursor'],str)
            loaded=list(page.json()['items'])
            cursor=page.json()['next_cursor']
            while cursor:
                response=await self.client.get(path+'/history',headers=self.auth,params={'limit':1,'cursor':cursor})
                self.assertEqual(response.status_code,200,response.text)
                loaded.extend(response.json()['items'])
                cursor=response.json()['next_cursor']
                self.assertLessEqual(len(loaded),3)
            self.assertEqual({item[key] for item in loaded},{item[key] for item in legacy.json()})
            self.assertEqual(len(loaded),3)
            self.assertEqual(page.headers['cache-control'],'no-store')
            self.assertNotIn('a'*40,page.text)
            self.assertFalse({'report','evidence','review','approval_id','checkpoint'} & page.json()['items'][0].keys())

    async def test_cross_queue_history_and_scope_cursors_are_not_interchangeable(self):
        case=(await self.client.get('/cases/history?limit=1',headers=self.auth)).json()['next_cursor']
        incident=(await self.client.get('/incidents/history?limit=1',headers=self.auth)).json()['next_cursor']
        history=(await self.client.get('/investigations/history?limit=1',headers=self.auth)).json()['next_cursor']
        for path,cursor,headers in (('/cases/history',incident,self.auth),('/incidents/history',case,self.auth),
                                    ('/cases/history',history,self.auth),('/incidents/history',history,self.auth),
                                    ('/cases/history',case,self.admin),('/incidents/history',incident,self.admin)):
            response=await self.client.get(path,headers=headers,params={'cursor':cursor})
            self.assertEqual(response.status_code,422,response.text)
            self.assertEqual(response.json(),{'error':'invalid_queue_cursor'})
        for path in ('/cases/history','/incidents/history'):
            for limit in ('0','101','bad'):
                self.assertEqual((await self.client.get(path,headers=self.auth,params={'limit':limit})).status_code,422)
            for cursor in ('','x'*513,'invalid+encoding'):
                response=await self.client.get(path,headers=self.auth,params={'cursor':cursor})
                self.assertEqual(response.status_code,422)
                self.assertEqual(response.json(),{'error':'invalid_queue_cursor'})

    async def test_all_source_scope_is_rechecked_before_next_page_limit(self):
        page=(await self.client.get('/incidents/history?limit=1',headers=self.auth)).json()
        self.assertEqual(page['items'][0]['id'],self.incidents[2]['id'])
        hidden=self.incidents[1]
        foreign_scope=self.store.begin(TENANT,'other-owner')
        self.store.finish(TENANT,'other-owner',foreign_scope,{'synthetic':True,'evidence':[]},'completed')
        linked=await self.client.post('/incidents/'+hidden['id']+'/investigations',headers=self.admin,
            json={'expected_revision':1,'investigation_id':foreign_scope,'comment':'Related case with different scope.'})
        self.assertEqual(linked.status_code,200,linked.text)
        response=await self.client.get('/incidents/history',headers=self.auth,params={'limit':1,'cursor':page['next_cursor']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual([item['id'] for item in response.json()['items']],[self.incidents[0]['id']])
        self.assertIsNone(response.json()['next_cursor'])
        self.assertNotIn(hidden['id'],response.text)

    async def test_case_assignment_revocation_and_current_permission_denial(self):
        source=self.store.begin(TENANT,'other-owner')
        self.store.finish(TENANT,'other-owner',source,{'synthetic':True,'evidence':[]},'completed')
        self.store.mutate_case(TENANT,'other-owner',source,0,'assign',assignee='demo-analyst')
        first=(await self.client.get('/cases/history?limit=1',headers=self.auth)).json()
        self.assertEqual(first['items'][0]['investigation_id'],source)
        self.store.mutate_case(TENANT,'other-owner',source,1,'assign',assignee=None)
        second=await self.client.get('/cases/history',headers=self.auth,params={'cursor':first['next_cursor']})
        self.assertEqual(second.status_code,200,second.text)
        self.assertNotIn(source,second.text)
        for path in ('/cases/history','/incidents/history'):
            route=next(route for route in self.app.routes if route.path==path)
            dependency=route.dependant.dependencies[0].call
            self.app.dependency_overrides[dependency]=lambda:ExecutionContext(TENANT,'demo-analyst',PERMISSIONS-{'cases:read'},CONNECTORS,True)
            response=await self.client.get(path,headers=self.auth,params={'cursor':first['next_cursor']})
            self.assertEqual(response.status_code,403)
            self.app.dependency_overrides.clear()


if __name__=='__main__': unittest.main()
