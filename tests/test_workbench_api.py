"""Workbench metadata/list authorization and no-cache/static security controls."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from work4ce_assistant.api import create_app,Settings,TENANT,PERMISSIONS,CONNECTORS,REVIEWER_PERMISSIONS
from work4ce_assistant.contracts import CapabilityManifest,ConnectorManifest,ExecutionContext,digest
from work4ce_assistant.fixtures import SEARCH_CAPABILITY,search_events
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.investigation import Investigator
from work4ce_assistant.storage import Store
from work4ce_assistant.web import PrivateResponses,mount_workbench


class Events:
    async def health(self): return True
    async def discover(self): return [SEARCH_CAPABILITY]
    async def invoke(self,capability_id,arguments): return search_events(arguments)


class WorkbenchAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=Store(':memory:')
        self.tools=Gateway(self.store)
        await self.tools.register(ConnectorManifest(connector_id='demo-rest',name='demo-rest',protocol='rest',tenant_id=TENANT,
            synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),Events(),reviewed=True)
        self.agent=Investigator(self.tools,self.store,require_review=True)
        self.own=await self.agent.investigate(ExecutionContext(TENANT,'demo-analyst',PERMISSIONS,CONNECTORS,True),'PowerShell')
        self.other=await self.agent.investigate(ExecutionContext(TENANT,'different-owner',PERMISSIONS,CONNECTORS,True),'benign')
        self.app=create_app(Settings('x'*40,'y'*40,require_human_review=True,reasoning_mode='fixture'),self.tools)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')
        self.auth={'Authorization':'Bearer '+'x'*40}
        self.admin={'Authorization':'Bearer '+'y'*40}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.store.close()

    async def test_me_is_authenticated_and_contains_no_credential(self):
        self.assertEqual((await self.client.get('/me')).status_code,401)
        response=await self.client.get('/me',headers=self.auth)
        self.assertEqual(response.status_code,200)
        me=response.json()
        self.assertEqual(me['subject'],'demo-analyst')
        self.assertEqual(me['tenant_id'],TENANT)
        self.assertTrue(me['review_required'])
        self.assertEqual(me['model_mode'],'fixture')
        self.assertNotIn('investigations:review',me['permissions'])
        self.assertNotIn('x'*40,response.text)
        admin=(await self.client.get('/me',headers=self.admin)).json()
        self.assertIn('investigations:review',admin['permissions'])
        self.assertEqual(response.headers['cache-control'],'no-store')

    async def test_case_list_is_owner_scoped_except_authorized_reviewers(self):
        self.assertEqual((await self.client.get('/investigations')).status_code,401)
        response=await self.client.get('/investigations?subject=different-owner&tenant=foreign',headers=self.auth)
        self.assertEqual([row['id'] for row in response.json()],[self.own['id']])
        row=response.json()[0]
        self.assertEqual(row['status'],'awaiting_review')
        self.assertEqual(row['query'],'PowerShell')
        self.assertEqual(row['evidence_count'],2)
        self.assertFalse({'review','review_id','comment','approval_id','report','evidence'} & row.keys())
        admin=await self.client.get('/investigations',headers=self.admin)
        self.assertEqual({row['id'] for row in admin.json()},{self.own['id'],self.other['id']})
        self.assertEqual(len((await self.client.get('/investigations?limit=1',headers=self.admin)).json()),1)
        for limit in ('0','101','invalid'):
            self.assertEqual((await self.client.get('/investigations?limit='+limit,headers=self.auth)).status_code,422)

    async def test_current_permissions_and_tenant_apply_to_lists(self):
        route=next(route for route in self.app.routes if route.path=='/investigations' and 'GET' in route.methods)
        dependency=route.dependant.dependencies[0].call
        self.app.dependency_overrides[dependency]=lambda:ExecutionContext('foreign','demo-analyst',PERMISSIONS,CONNECTORS,True)
        self.assertEqual((await self.client.get('/investigations',headers=self.auth)).json(),[])
        self.app.dependency_overrides[dependency]=lambda:ExecutionContext(TENANT,'demo-analyst',frozenset(),CONNECTORS,True)
        self.assertEqual((await self.client.get('/investigations',headers=self.auth)).status_code,403)
        self.app.dependency_overrides.clear()

    async def test_history_page_route_preserves_legacy_array_and_summary_privacy(self):
        self.assertEqual((await self.client.get('/investigations/history')).status_code,401)
        legacy=await self.client.get('/investigations',headers=self.auth)
        page=await self.client.get('/investigations/history?subject=different-owner&tenant=foreign',headers=self.auth)
        self.assertEqual(page.status_code,200,page.text)
        self.assertIsInstance(legacy.json(),list)
        self.assertEqual(page.json(),{'items':legacy.json(),'next_cursor':None})
        self.assertFalse({'review','review_id','reviewer','comment','approval_id','report','evidence'} & page.json()['items'][0].keys())
        self.assertEqual(page.headers['cache-control'],'no-store')
        # The literal history route must be registered before /{identity}.
        self.assertEqual(set(page.json()),{'items','next_cursor'})

    async def test_admin_history_uses_cursor_and_owner_cannot_reuse_it(self):
        first=await self.client.get('/investigations/history?limit=1',headers=self.admin)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(len(first.json()['items']),1)
        cursor=first.json()['next_cursor']
        self.assertIsInstance(cursor,str)
        second=await self.client.get('/investigations/history',params={'limit':1,'cursor':cursor},headers=self.admin)
        self.assertIsNone(second.json()['next_cursor'])
        self.assertEqual({row['id'] for row in first.json()['items']+second.json()['items']},{self.own['id'],self.other['id']})
        denied=await self.client.get('/investigations/history',params={'cursor':cursor},headers=self.auth)
        self.assertEqual(denied.status_code,422)
        self.assertEqual(denied.json(),{'error':'invalid_history_cursor'})
        # Publicly forgeable scope hashes are not permissions: SQL still limits an
        # analyst to their own records even with a fabricated future position.
        payload={'v':1,'scope':digest({'tenant':TENANT,'subject':'demo-analyst'}),
            'created_at':'9999-01-01T00:00:00+00:00','id':'ffffffff-ffff-ffff-ffff-ffffffffffff'}
        forged=base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        response=await self.client.get('/investigations/history',params={'cursor':forged,'subject':'different-owner'},headers=self.auth)
        self.assertEqual([row['id'] for row in response.json()['items']],[self.own['id']])

    async def test_history_rechecks_current_permissions_tenant_and_role_scope(self):
        for index in range(2):
            identity=self.store.begin(TENANT,'demo-analyst')
            self.store.finish(TENANT,'demo-analyst',identity,{'query':'extra-'+str(index),'synthetic':True},'completed')
        page=(await self.client.get('/investigations/history?limit=1',headers=self.auth)).json()
        cursor=page['next_cursor']
        route=next(route for route in self.app.routes if route.path=='/investigations/history' and 'GET' in route.methods)
        dependency=route.dependant.dependencies[0].call
        self.app.dependency_overrides[dependency]=lambda:ExecutionContext(TENANT,'demo-analyst',frozenset(),CONNECTORS,True)
        response=await self.client.get('/investigations/history',params={'cursor':cursor},headers=self.auth)
        self.assertEqual(response.status_code,403)
        self.app.dependency_overrides[dependency]=lambda:ExecutionContext('foreign','demo-analyst',PERMISSIONS,CONNECTORS,True)
        response=await self.client.get('/investigations/history',params={'cursor':cursor},headers=self.auth)
        self.assertEqual(response.status_code,422)
        self.assertEqual((await self.client.get('/investigations/history',headers=self.auth)).json(),{'items':[],'next_cursor':None})
        self.app.dependency_overrides[dependency]=lambda:ExecutionContext(TENANT,'demo-analyst',REVIEWER_PERMISSIONS,CONNECTORS,True)
        self.assertEqual((await self.client.get('/investigations/history',params={'cursor':cursor},headers=self.auth)).status_code,422)
        self.app.dependency_overrides.clear()

    async def test_history_rejects_invalid_limits_and_cursors(self):
        for limit in ('0','101','bad'):
            self.assertEqual((await self.client.get('/investigations/history',params={'limit':limit},headers=self.auth)).status_code,422)
        for cursor in ('','x'*513,'bad+encoding','not-a-cursor'):
            response=await self.client.get('/investigations/history',params={'cursor':cursor},headers=self.auth)
            self.assertEqual(response.status_code,422,response.text)
            self.assertEqual(response.json(),{'error':'invalid_history_cursor'})

    async def test_sensitive_success_and_error_responses_not_cached(self):
        for path,headers in (('/me',{}),('/me',self.auth),('/investigations',self.auth),
                             ('/investigations/'+self.own['id'],self.auth),('/reviews',self.auth)):
            response=await self.client.get(path,headers=headers)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(response.headers['x-content-type-options'],'nosniff')
            self.assertEqual(response.headers['referrer-policy'],'no-referrer')
            self.assertEqual(response.headers['x-frame-options'],'DENY')


class StaticWorkbenchTests(unittest.IsolatedAsyncioTestCase):
    async def test_html_hash_policy_allows_build_scripts_without_unsafe_inline(self):
        with tempfile.TemporaryDirectory() as directory:
            assets=Path(directory)
            (assets/'index.html').write_text('<html><script>window.fixture=true;</script><body>Workbench</body></html>')
            (assets/'app.js').write_text('console.log("fixture")')
            app=FastAPI()
            app.add_middleware(PrivateResponses)
            mount_workbench(app,assets)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
                response=await client.get('/workbench/')
                self.assertEqual(response.status_code,200)
                policy=response.headers['content-security-policy']
                self.assertIn("'sha256-",policy)
                self.assertNotIn('unsafe-inline',policy)
                self.assertNotIn('unsafe-eval',policy)
                self.assertIn("connect-src 'self'",policy)
                self.assertIn("frame-ancestors 'none'",policy)
                self.assertEqual(response.headers['cache-control'],'no-store')
                self.assertEqual((await client.get('/workbench/app.js')).status_code,200)
                self.assertEqual((await client.get('/workbench/../pyproject.toml')).status_code,404)

    async def test_unbuilt_dashboard_does_not_hide_backend_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            app=FastAPI()
            mount_workbench(app,Path(directory))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
                response=await client.get('/workbench/')
                self.assertEqual(response.status_code,503)
                self.assertEqual(response.json(),{'error':'workbench_not_built'})
