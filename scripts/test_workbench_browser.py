"""Real Chromium workflow tests against local API/reference services.

Credentials are generated per run and never written to source or screenshots.
No production credentials, live model, external browser URL or response adapter.
"""
import asyncio
from contextlib import ExitStack
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import httpx
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def stop(process):
    if process.poll() is None:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


class WorkbenchBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack=ExitStack()
        try:
            directory=Path(cls.stack.enter_context(tempfile.TemporaryDirectory()))
            log=cls.stack.enter_context(open(directory/'services.log','w+'))
            cls.analyst=secrets.token_urlsafe(40)
            cls.reviewer=secrets.token_urlsafe(40)
            cls.api_port,rest_port=port(),port()
            cls.base=f'http://127.0.0.1:{cls.api_port}'
            cls.database=str(directory/'browser.db')
            environment={**os.environ,'PYTHONPATH':str(ROOT/'src'),'WORK4CE_MODE':'demo','WORK4CE_AUTH_MODE':'demo',
                'WORK4CE_DEMO_TOKEN':cls.analyst,'WORK4CE_ADMIN_TOKEN':cls.reviewer,
                'WORK4CE_DB':cls.database,'WORK4CE_REST_URL':f'http://127.0.0.1:{rest_port}',
                'WORK4CE_REQUIRE_HUMAN_REVIEW':'true','WORK4CE_REASONING_MODE':'fixture',
                'WORK4CE_MAX_MODEL_CALLS':'4','WORK4CE_MAX_MODEL_TOKENS':'36000','WORK4CE_MAX_MODEL_COST_MICROUSD':'1000000',
                'WORK4CE_MAX_TOOL_CALLS':'2','WORK4CE_INVESTIGATION_TIMEOUT_SECONDS':'120'}
            cls.markup_id=asyncio.run(cls.seed_markup(environment['WORK4CE_DB']))
            for command in ([sys.executable,'-m','work4ce_assistant.reference_servers','rest','--port',str(rest_port)],
                            [sys.executable,'-m','work4ce_assistant','serve','--port',str(cls.api_port)]):
                process=subprocess.Popen(command,env=environment,cwd=ROOT,stdout=log,stderr=log)
                cls.stack.callback(stop,process)
            cls.http=cls.stack.enter_context(httpx.Client(base_url=cls.base,trust_env=False,timeout=40))
            for _ in range(160):
                try:
                    if cls.http.get('/ready',headers={'Authorization':'Bearer '+cls.analyst}).status_code==200:
                        break
                except httpx.HTTPError: pass
                time.sleep(.05)
            else: raise RuntimeError('Browser fixture services did not become ready')
            cls.workbench=cls.base+'/workbench/'
            if cls.http.get('/workbench/').status_code!=200:
                raise RuntimeError('Build the dashboard before running browser checks')
            executable=os.environ.get('WORK4CE_BROWSER_EXECUTABLE') or next((shutil.which(name) for name in
                ('chromium','chromium-browser','google-chrome','google-chrome-stable') if shutil.which(name)),None)
            if not executable: raise RuntimeError('A Chromium/Chrome executable is required')
            playwright=cls.stack.enter_context(sync_playwright())
            cls.browser=playwright.chromium.launch(executable_path=executable,headless=True)
            cls.stack.callback(cls.browser.close)
            (ROOT/'.local').mkdir(exist_ok=True)
        except Exception:
            cls.stack.close()
            raise

    @staticmethod
    async def seed_markup(database):
        from work4ce_assistant.api import TENANT,PERMISSIONS,CONNECTORS
        from work4ce_assistant.contracts import CapabilityManifest,ConnectorManifest,ExecutionContext
        from work4ce_assistant.fixtures import SEARCH_CAPABILITY
        from work4ce_assistant.gateway import Gateway
        from work4ce_assistant.investigation import Investigator
        from work4ce_assistant.storage import Store
        class Events:
            async def health(self): return True
            async def discover(self): return [SEARCH_CAPABILITY]
            async def invoke(self,capability_id,arguments):
                return {'events':[{'id':'markup-fixture','timestamp':'2026-10-29T06:00:00Z','kind':'untrusted_log',
                    'summary':'<img src=x onerror="window.__work4ce_xss=true"> Untrusted synthetic markup',
                    'synthetic':True}]}
        store=Store(database)
        try:
            gateway=Gateway(store)
            await gateway.register(ConnectorManifest(connector_id='demo-rest',name='demo-rest',protocol='rest',
                tenant_id=TENANT,synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),Events(),reviewed=True)
            result=await Investigator(gateway,store,require_review=True).investigate(
                ExecutionContext(TENANT,'demo-analyst',PERMISSIONS,CONNECTORS,True),'Markup safety check')
            return result['id']
        finally: store.close()

    @classmethod
    def tearDownClass(cls): cls.stack.close()

    def setUp(self):
        self.context=self.browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Africa/Nairobi')
        self.page=self.context.new_page()
        self.page.set_default_timeout(12000)
        self.policy_errors=[]
        self.page.on('console',lambda message:self.policy_errors.append(message.text) if
            'Content Security Policy' in message.text or 'Refused to execute' in message.text else None)
        self.page.goto(self.workbench)

    def tearDown(self):
        self.context.close()

    def login(self,credential):
        self.page.get_by_label('Access token',exact=True).fill(credential)
        self.page.get_by_role('button',name='Connect to workspace',exact=True).click()
        expect(self.page.get_by_role('navigation',name='Workspace navigation')).to_be_visible()
        expect(self.page.get_by_test_id('case-row-'+self.markup_id)).to_be_visible()

    def logout(self):
        self.page.get_by_role('button',name='Sign out',exact=True).click()
        expect(self.page.get_by_label('Access token',exact=True)).to_be_visible()
        self.assertTrue(self.page.get_by_label('Access token',exact=True).input_value()=='','Token field was not cleared')

    def navigate(self,name):
        self.page.get_by_role('navigation',name='Workspace navigation').get_by_role('button',name=re.compile('^'+name)).click()

    def test_analyst_reviewer_simulation_flow(self):
        self.login(self.analyst)
        self.assertEqual(self.page.get_by_role('navigation').get_by_role('button',name=re.compile('^Review queue')).count(),0)
        self.page.get_by_role('button',name='New investigation',exact=True).first.click()
        dialog=self.page.get_by_role('dialog',name='Start an investigation')
        dialog.get_by_label('Investigation query',exact=True).fill('PowerShell')
        with self.page.expect_response(lambda response: response.request.method=='POST' and response.url.endswith('/investigations')) as event:
            dialog.get_by_role('button',name='Investigate',exact=True).click()
        response=event.value
        self.assertEqual(response.status,201)
        case=response.json()
        identity=case['id']
        expect(self.page.get_by_role('region',name='Investigation report')).to_be_visible()
        expect(self.page.get_by_text('Suspicious PowerShell encoded command on demo-host-1',exact=True)).to_be_visible()
        self.assertEqual(self.page.get_by_role('button',name='Approve report',exact=True).count(),0)
        self.page.get_by_role('button',name='Evidence 1',exact=True).first.click()
        expect(self.page.get_by_test_id('evidence-'+case['report']['evidence'][0]['evidence_id'])).to_have_class(re.compile('highlight'))
        self.page.get_by_role('button',name='Evidence 2',exact=True).first.click()
        expect(self.page.get_by_test_id('evidence-'+case['report']['evidence'][1]['evidence_id'])).to_have_class(re.compile('highlight'))
        self.page.screenshot(path=str(ROOT/'.local'/'workbench-desktop.png'),full_page=True)
        self.logout()
        self.login(self.reviewer)
        self.navigate('Review queue')
        self.page.get_by_test_id('review-row-'+identity).click()
        self.page.get_by_role('button',name='Approve report',exact=True).click()
        dialog=self.page.get_by_role('dialog',name='Approve report review')
        dialog.locator('#comment').fill('Reviewed the synthetic evidence and source attribution.')
        dialog.get_by_role('button',name='Approve',exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(self.page.get_by_text('Report review approved.',exact=True)).to_be_visible()
        self.logout()
        self.login(self.analyst)
        self.page.get_by_test_id('case-row-'+identity).click()
        self.page.get_by_role('button',name='Propose',exact=True).click()
        dialog=self.page.get_by_role('dialog',name='Propose a synthetic dry run')
        dialog.get_by_label('Observed synthetic target',exact=True).select_option('demo-host-1')
        with self.page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/responses')) as event:
            dialog.get_by_role('button',name='Request approval',exact=True).click()
        self.assertEqual(event.value.status,201)
        proposal=event.value.json()
        expect(dialog).not_to_be_visible()
        self.logout()
        self.login(self.reviewer)
        self.navigate('Response approvals')
        row=self.page.get_by_test_id('response-row-'+proposal['id'])
        row.get_by_role('button',name='Approve dry run',exact=True).click()
        dialog=self.page.get_by_role('dialog',name='Approve dry-run request')
        dialog.get_by_role('button',name='Approve',exact=True).click()
        expect(dialog).not_to_be_visible()
        self.logout()
        self.login(self.analyst)
        self.navigate('Response approvals')
        row=self.page.get_by_test_id('response-row-'+proposal['id'])
        row.get_by_role('button',name='Record simulation',exact=False).click()
        dialog=self.page.get_by_role('dialog',name='Record this simulation?')
        with self.page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/simulate')) as event:
            dialog.get_by_role('button',name='Record dry run',exact=True).click()
        self.assertEqual(event.value.status,200)
        result=event.value.json()
        self.assertFalse(result['simulation_result']['performed'])
        expect(row.get_by_text('Simulation recorded',exact=True)).to_be_visible()
        self.assertEqual(row.get_by_role('button',name='Record simulation',exact=False).count(),0)
        self.assertEqual(self.policy_errors,[])

    def test_memory_only_session_and_untrusted_markup(self):
        self.login(self.analyst)
        self.page.get_by_test_id('case-row-'+self.markup_id).click()
        report=self.page.get_by_role('region',name='Investigation report')
        expect(report.get_by_text('<img src=x onerror="window.__work4ce_xss=true"> Untrusted synthetic markup',exact=True)).to_be_visible()
        self.assertEqual(report.locator('img').count(),0)
        self.assertFalse(self.page.evaluate('Boolean(window.__work4ce_xss)'))
        self.assertEqual(self.page.evaluate('localStorage.length'),0)
        self.assertEqual(self.page.evaluate('sessionStorage.length'),0)
        self.assertEqual(self.context.cookies(),[])
        self.page.reload()
        expect(self.page.get_by_label('Access token',exact=True)).to_be_visible()
        self.assertEqual(self.page.get_by_role('region',name='Investigation report').count(),0)
        self.assertEqual(self.policy_errors,[])

    def test_mobile_layout_remains_usable(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.login(self.analyst)
        self.page.get_by_test_id('case-row-'+self.markup_id).click()
        expect(self.page.get_by_role('region',name='Investigation report')).to_be_visible()
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'),'Mobile page overflows horizontally')
        self.page.screenshot(path=str(ROOT/'.local'/'workbench-mobile.png'),full_page=True)
        self.logout()
        self.assertEqual(self.policy_errors,[])

    def test_paginated_history_and_refresh_fence(self):
        from sqlalchemy import update
        from work4ce_assistant.api import TENANT
        from work4ce_assistant.storage import Store,investigations
        store=Store(self.database)
        try:
            identities=[]
            for index in range(55):
                identity=store.begin(TENANT,'demo-analyst')
                store.finish(TENANT,'demo-analyst',identity,{'synthetic':True,'query':f'Archived synthetic case {index}',
                    'assessment':'needs_analyst_review','evidence':[],'findings':[]},'completed')
                identities.append(identity)
            # Tied old timestamps exercise the ID tie-breaker across page boundaries.
            with store.engine.begin() as connection:
                connection.execute(update(investigations).where(investigations.c.id.in_(identities)).values(
                    created_at='2025-01-01T00:00:00+00:00'))
        finally: store.close()
        self.login(self.analyst)
        rows=self.page.locator('[data-testid^="case-row-"]')
        expect(rows).to_have_count(50)
        older=self.page.get_by_role('button',name='Load older investigations',exact=True)
        expect(older).to_be_visible()
        held=[]
        def intercept(route):
            if 'cursor=' in route.request.url:
                held.append((route,route.fetch()))
            else: route.continue_()
        self.page.route('**/investigations/history?*',intercept)
        older.click()
        expect(self.page.get_by_role('button',name='Loading older investigations…',exact=True)).to_be_visible()
        # A refresh must win over an older page response from before that refresh.
        self.page.get_by_role('button',name='Refresh',exact=True).click()
        expect(older).to_be_enabled()
        self.assertEqual(len(held),1)
        held[0][0].fulfill(response=held[0][1])
        self.page.unroute('**/investigations/history?*',intercept)
        # Wait for the stale response handler itself before asserting it was ignored.
        self.page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        expect(rows).to_have_count(50)
        with self.page.expect_response(lambda response:'cursor=' in response.url and '/investigations/history?' in response.url) as event:
            older.click()
        self.assertEqual(event.value.status,200)
        page=event.value.json()
        self.assertIsNone(page['next_cursor'])
        expect(rows).to_have_count(50+len(page['items']))
        row_ids=rows.evaluate_all('(items) => items.map(item => item.dataset.testid)')
        self.assertEqual(len(row_ids),len(set(row_ids)))
        for identity in identities:
            self.assertIn('case-row-'+identity,row_ids)
        expect(older).not_to_be_visible()
        oldest=sorted(identities)[0]
        self.page.get_by_test_id('case-row-'+oldest).click()
        expect(self.page.get_by_role('region',name='Investigation report')).to_be_visible()
        self.page.get_by_label('Search loaded investigations',exact=True).fill('Archived synthetic case ')
        expect(rows).to_have_count(55)
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'))
        self.logout()
        self.login(self.reviewer)
        self.assertEqual(self.page.get_by_role('button',name='Load older investigations',exact=True).count(),1)
        expect(rows).to_have_count(50)
        self.assertEqual(self.policy_errors,[])


if __name__=='__main__':
    unittest.main(verbosity=2)
