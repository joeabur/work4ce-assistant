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

    def run_workflow(self, database=None):
        with tempfile.TemporaryDirectory() as directory:
            rest_port, api_port = free_port(), free_port()
            analyst, admin = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
            env = {**os.environ, 'WORK4CE_DEMO_TOKEN':analyst, 'WORK4CE_ADMIN_TOKEN':admin,
                   'WORK4CE_AUTH_MODE':'demo', 'WORK4CE_MODE':'demo', 'WORK4CE_DB':database or str(Path(directory)/'demo.db'), 'WORK4CE_REST_URL':f'http://127.0.0.1:{rest_port}'}
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
