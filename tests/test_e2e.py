"""Actual API -> gateway -> REST/MCP -> stored evidence acceptance test."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import httpx


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


class VerticalSliceTests(unittest.TestCase):
    def test_authenticated_protocol_replacement_and_restart(self):
        self.run_workflow()

    @unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'), 'PostgreSQL API integration requires WORK4CE_TEST_POSTGRES_URL')
    def test_postgres_authenticated_protocol_replacement_and_restart(self):
        from work4ce_assistant.storage import migrate
        database = os.environ['WORK4CE_TEST_POSTGRES_URL']
        migrate(database)
        self.run_workflow(database)

    def test_fixture_models_use_real_tools_and_survive_crash(self):
        self.run_workflow(reasoning_mode='fixture')

    @unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'), 'PostgreSQL model integration requires WORK4CE_TEST_POSTGRES_URL')
    def test_postgres_fixture_models_use_real_tools_and_survive_crash(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        from uuid import uuid4
        from work4ce_assistant.storage import migrate
        url=make_url(os.environ['WORK4CE_TEST_POSTGRES_URL'])
        engine=create_engine(url,hide_parameters=True)
        schema='model_e2e_'+uuid4().hex
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE SCHEMA '+schema))
            database=url.update_query_dict({'options':'-csearch_path='+schema}).render_as_string(hide_password=False)
            migrate(database)
            self.run_workflow(database,reasoning_mode='fixture')
        finally:
            with engine.begin() as connection:
                connection.execute(text('DROP SCHEMA '+schema+' CASCADE'))
            engine.dispose()

    def run_workflow(self, database=None, *, reasoning_mode='deterministic'):
        with tempfile.TemporaryDirectory() as directory:
            rest_port, api_port = free_port(), free_port()
            analyst, admin = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
            env = {**os.environ, 'WORK4CE_DEMO_TOKEN':analyst, 'WORK4CE_ADMIN_TOKEN':admin,
                   'WORK4CE_REASONING_MODE':reasoning_mode, 'WORK4CE_AUTH_MODE':'demo', 'WORK4CE_MODE':'demo', 'WORK4CE_DB':database or str(Path(directory)/'demo.db'), 'WORK4CE_REST_URL':f'http://127.0.0.1:{rest_port}'}
            log = open(Path(directory)/'services.log', 'w+')
            rest = subprocess.Popen([sys.executable,'-m','work4ce_assistant.reference_servers','rest','--port',str(rest_port)],
                                    env=env,stdout=log,stderr=log)
            api = None
            client = httpx.Client(base_url=f'http://127.0.0.1:{api_port}',trust_env=False,timeout=30)
            auth, administration = {'Authorization':'Bearer '+analyst}, {'Authorization':'Bearer '+admin}

            def wait(path, headers=None):
                for _ in range(150):
                    try:
                        response = client.get(path,headers=headers)
                        if response.status_code == 200:
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(.05)
                self.fail('Service readiness timed out')

            def start_api():
                process = subprocess.Popen([sys.executable,'-m','work4ce_assistant','serve','--port',str(api_port)],
                                           env=env,stdout=log,stderr=log)
                return process

            try:
                # Explicitly await fixture startup before API connector bootstrap.
                with httpx.Client(trust_env=False) as fixture_client:
                    for _ in range(100):
                        try:
                            if fixture_client.get(f'http://127.0.0.1:{rest_port}/health').status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.05)
                    else:
                        self.fail('REST fixture startup failed')
                api = start_api()
                wait('/ready', auth)
                self.assertEqual(client.post('/investigations',json={'query':'PowerShell'}).status_code,401)
                connectors = client.get('/connectors',headers=auth).json()
                self.assertEqual({x['protocol'] for x in connectors},{'rest','mcp'})
                self.assertEqual(len(client.get('/capabilities',headers=auth).json()),1)
                # A queued job survives API shutdown; a separate worker then exits
                # abruptly after checkpoint commit, before report commit.
                queued_headers = {**auth, 'Idempotency-Key':'durable-e2e-checkpoint'}
                queued = client.post('/investigations',json={'query':'PowerShell','defer':True},headers=queued_headers)
                self.assertEqual(queued.status_code,202,queued.text)
                workflow_id = queued.json()['id']
                self.assertEqual(client.get('/investigations/'+workflow_id+'/state',headers=auth).json()['status'],'queued')
                api.terminate()
                api.wait(timeout=5)
                worker_code = """
import asyncio, os
from work4ce_assistant.api import TENANT,PERMISSIONS,CONNECTORS
from work4ce_assistant.connectors import RestConnector
from work4ce_assistant.contracts import CapabilityManifest,ConnectorManifest,ExecutionContext
from work4ce_assistant.fixtures import SEARCH_CAPABILITY
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.investigation import Investigator
from work4ce_assistant.storage import Store
async def run():
    store=Store(os.environ['WORK4CE_DB'])
    gateway=Gateway(store)
    await gateway.register(ConnectorManifest(connector_id='demo-rest',name='demo-rest',protocol='rest',
        tenant_id=TENANT,synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),
        RestConnector(os.environ['WORK4CE_REST_URL']),reviewed=True)
    claim=store.claim_workflow
    store.claim_workflow=lambda *args,**kwargs: claim(*args,lease_seconds=2)
    store.finish_workflow=lambda *args,**kwargs: os._exit(73)
    reasoner=None
    if os.environ.get('WORK4CE_REASONING_MODE')=='fixture':
        from work4ce_assistant.models import ModelGateway,FixtureProvider
        from work4ce_assistant.reasoning import Reasoner
        reasoner=Reasoner(ModelGateway(FixtureProvider()),store)
    await Investigator(gateway,store,reasoner=reasoner).resume(ExecutionContext(TENANT,'demo-analyst',PERMISSIONS,CONNECTORS,True),
        os.environ['WORK4CE_TEST_WORKFLOW_ID'])
asyncio.run(run())
"""
                child = subprocess.run([sys.executable,'-c',worker_code],
                    env={**env,'WORK4CE_TEST_WORKFLOW_ID':workflow_id},stdout=log,stderr=log,timeout=15)
                self.assertEqual(child.returncode,73)
                from work4ce_assistant.storage import Store
                state_store = Store(env['WORK4CE_DB'])
                try:
                    saved_checkpoint = state_store.get_workflow('synthetic-demo','demo-analyst',workflow_id)['checkpoint']
                    self.assertIsNotNone(saved_checkpoint)
                finally:
                    state_store.close()
                requests_before_resume = (Path(directory)/'services.log').read_text().count('POST /events/search')
                api = start_api()
                wait('/ready',auth)
                for _ in range(50):
                    resumed = client.post('/investigations/'+workflow_id+'/resume',headers=auth)
                    if resumed.status_code == 409 and resumed.json().get('error') == 'workflow_busy':
                        time.sleep(.1)
                        continue
                    break
                self.assertEqual(resumed.status_code,200,resumed.text)
                self.assertEqual(resumed.json()['report']['evidence'],saved_checkpoint['evidence'])
                self.assertEqual((Path(directory)/'services.log').read_text().count('POST /events/search'),requests_before_resume)
                replay = client.post('/investigations',json={'query':'PowerShell'},headers=queued_headers)
                self.assertEqual(replay.status_code,201,replay.text)
                self.assertEqual(replay.json(),resumed.json())
                if reasoning_mode=='fixture':
                    self.assertEqual(resumed.json()['report']['engine'],'structured-fixture-v1')
                    self.assertTrue(resumed.json()['report']['reasoning']['synthetic_fixture'])
                    self.assertEqual(resumed.json()['report']['reasoning']['usage']['calls'],2)
                    state=client.get('/investigations/'+workflow_id+'/state',headers=auth).json()
                    self.assertEqual(state['model_usage']['calls'],2)
                conflict = client.post('/investigations',json={'query':'different'},headers=queued_headers)
                self.assertEqual(conflict.status_code,409)
                cancel_job = client.post('/investigations',json={'query':'PowerShell','defer':True},
                    headers={**auth,'Idempotency-Key':'durable-e2e-cancel'})
                self.assertEqual(cancel_job.status_code,202,cancel_job.text)
                cancel_id = cancel_job.json()['id']
                self.assertEqual(client.post('/investigations/'+cancel_id+'/cancel',headers=auth).json()['status'],'cancelled')
                self.assertEqual(client.post('/investigations/'+cancel_id+'/resume',headers=auth).status_code,409)
                first = client.post('/investigations',json={'query':'PowerShell'},headers=auth)
                self.assertEqual(first.status_code,201,first.text)
                self.assertEqual(first.json()['report']['evidence'][0]['protocol'],'rest')
                self.assertEqual(client.post('/connectors/demo-rest/disable',headers=auth).status_code,403)
                self.assertEqual(client.post('/connectors/demo-rest/disable',headers=administration).status_code,200)
                second = client.post('/investigations',json={'query':'PowerShell'},headers=auth)
                self.assertEqual(second.status_code,201,second.text)
                self.assertEqual(second.json()['report']['evidence'][0]['protocol'],'mcp')
                for report in (first.json()['report'],second.json()['report']):
                    ids = {e['evidence_id'] for e in report['evidence']}
                    self.assertEqual(len(ids),2)
                    self.assertTrue(all(set(f['evidence_ids']) <= ids for f in report['findings']))
                identity = second.json()['id']
                api.terminate()
                api.wait(timeout=5)
                api = start_api()
                wait('/ready',auth)
                restored = client.get('/investigations/'+identity,headers=auth)
                self.assertEqual(restored.json(),second.json())
                states = {x['connector_id']:x['enabled'] for x in client.get('/connectors',headers=auth).json()}
                self.assertFalse(states['demo-rest'])
                third = client.post('/investigations',json={'query':'PowerShell'},headers=auth)
                self.assertEqual(third.status_code,201,third.text)
                self.assertEqual(third.json()['report']['evidence'][0]['connector_id'],'demo-mcp')
                self.assertEqual(client.post('/connectors/demo-mcp/disable',headers=administration).status_code,200)
                self.assertEqual(client.get('/ready',headers=auth).status_code,503)
                self.assertEqual(client.post('/investigations',json={'query':'PowerShell'},headers=auth).status_code,403)
            finally:
                client.close()
                for process in (api,rest):
                    if process is not None:
                        process.terminate()
                        process.wait(timeout=5)
                log.close()
