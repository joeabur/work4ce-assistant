"""Signed-token API tests: identity claims never supply authorization grants."""
import json
import time
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from work4ce_assistant.api import Settings, create_app, TENANT
from work4ce_assistant.auth import OIDCConfig, OIDCVerifier
from work4ce_assistant.contracts import CapabilityManifest, ConnectorManifest, Work4ceError
from work4ce_assistant.fixtures import SEARCH_CAPABILITY, search_events
from work4ce_assistant.gateway import Gateway
from work4ce_assistant.storage import Store


class Adapter:
    async def discover(self):
        return [SEARCH_CAPABILITY]
    async def health(self):
        return True
    async def invoke(self, capability_id, arguments):
        return search_events(arguments)


class OIDCAPIIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    async def asyncSetUp(self):
        self.config = OIDCConfig('https://identity.example.test/synthetic','work4ce','https://identity.example.test/jwks')
        self.jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key())), 'kid':'test','alg':'RS256'}
        self.jwks_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
            httpx.Response(200,json={'keys':[self.jwk]})))
        self.verifier = OIDCVerifier(self.config,self.jwks_client)
        self.store = Store(':memory:')
        self.gateway = Gateway(self.store)
        await self.gateway.register(ConnectorManifest(connector_id='demo-rest',name='Demo REST',
            protocol='rest',tenant_id=TENANT,synthetic=True,capability=CapabilityManifest(**SEARCH_CAPABILITY)),
            Adapter(), reviewed=True)
        self.settings = Settings(auth_mode='oidc',oidc_config=self.config,
            oidc_subject_roles=(('analyst-sub','analyst'),('admin-sub','admin')))
        self.app = create_app(self.settings,self.gateway,verifier=self.verifier)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://api')

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.jwks_client.aclose()
        self.store.close()

    def headers(self, subject='analyst-sub', **claims):
        current = int(time.time())
        token = jwt.encode({'iss':self.config.issuer,'aud':'work4ce','sub':subject,
            'iat':current-1,'exp':current+120,**claims},self.key,algorithm='RS256',headers={'kid':'test','typ':'at+jwt'})
        return {'Authorization':'Bearer '+token}

    async def test_authenticated_investigation_uses_server_assigned_context(self):
        response = await self.client.post('/investigations',json={'query':'PowerShell'},
            headers=self.headers(tenant='attacker',roles=['admin'],permissions=['*']))
        self.assertEqual(response.status_code,201,response.text)
        report = response.json()['report']
        self.assertEqual(report['tenant_id'],TENANT)
        self.assertEqual(len(report['evidence']),2)
        rows = self.store.audit_rows(TENANT)
        self.assertIn(('capability.execute','demo-rest','succeeded'),rows)
        denied = await self.client.post('/connectors/demo-rest/disable',headers=self.headers(roles=['admin']))
        self.assertEqual(denied.status_code,403)

    async def test_only_server_mapped_admin_can_disable(self):
        denied = await self.client.post('/connectors/demo-rest/disable',headers=self.headers('unknown-sub',roles=['admin']))
        self.assertEqual(denied.status_code,403)
        success = await self.client.post('/connectors/demo-rest/disable',headers=self.headers('admin-sub'))
        self.assertEqual(success.status_code,200)

    async def test_static_demo_tokens_never_fallback_in_oidc_mode(self):
        for headers in ({},{'Authorization':'Bearer '+('x'*40)}):
            self.assertEqual((await self.client.get('/connectors',headers=headers)).status_code,401)
        self.assertEqual((await self.client.get('/connectors',headers=self.headers(exp=int(time.time())-1))).status_code,401)

    async def test_jwks_outage_is_redacted_and_does_not_invoke(self):
        async def unavailable(request):
            raise httpx.ConnectError('sensitive diagnostic')
        await self.jwks_client.aclose()
        self.jwks_client = httpx.AsyncClient(transport=httpx.MockTransport(unavailable))
        self.verifier._client = self.jwks_client
        response = await self.client.post('/investigations',json={'query':'PowerShell'},headers=self.headers())
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json(),{'error':'auth_service_unavailable'})
        self.assertNotIn('sensitive',response.text)

    def test_configuration_rejects_partial_or_unsafe_role_mappings(self):
        for arguments in ({'auth_mode':'unknown'},{'auth_mode':'oidc'},
            {'auth_mode':'oidc','oidc_config':self.config,'oidc_subject_roles':(('sub','superuser'),)},
            {'auth_mode':'oidc','oidc_config':{},'oidc_subject_roles':(('sub','admin'),)},
            {'auth_mode':'oidc','oidc_config':self.config,'oidc_subject_roles':(('sub',['admin']),)},
            {'auth_mode':'oidc','oidc_config':self.config,'oidc_subject_roles':(('sub','admin'),('sub','analyst'))},
            {'mode':'production','auth_mode':'oidc','oidc_config':self.config,'oidc_subject_roles':(('sub','admin'),)}):
            with self.subTest(arguments=arguments),self.assertRaises(ValueError):
                Settings(**arguments)

    def test_environment_selects_oidc_without_requiring_demo_secrets(self):
        variables={'WORK4CE_AUTH_MODE':'oidc','WORK4CE_OIDC_ISSUER':self.config.issuer,
            'WORK4CE_OIDC_AUDIENCE':self.config.audience,'WORK4CE_OIDC_JWKS_URL':self.config.jwks_url,
            'WORK4CE_OIDC_SUBJECT_ROLES':'{"analyst-sub":"analyst"}'}
        with patch.dict('os.environ',variables,clear=True):
            settings=Settings.from_environment()
        self.assertEqual(settings.auth_mode,'oidc')
        self.assertEqual(settings.demo_token,'')
        self.assertNotIn('password',repr(settings))

    def test_duplicate_environment_subjects_fail_closed(self):
        variables={'WORK4CE_AUTH_MODE':'oidc','WORK4CE_OIDC_ISSUER':self.config.issuer,
            'WORK4CE_OIDC_AUDIENCE':self.config.audience,'WORK4CE_OIDC_JWKS_URL':self.config.jwks_url,
            'WORK4CE_OIDC_SUBJECT_ROLES':'{"same-sub":"analyst","same-sub":"admin"}'}
        with patch.dict('os.environ',variables,clear=True),self.assertRaises(ValueError):
            Settings.from_environment()

    async def test_owned_verifier_and_store_close_on_failed_bootstrap(self):
        stub=SimpleNamespace(close=AsyncMock())
        with patch('work4ce_assistant.api.OIDCVerifier',return_value=stub), \
             patch.object(Gateway,'register',new=AsyncMock(side_effect=Work4ceError('connector_discovery_failed',503))):
            app=create_app(Settings(database=':memory:',auth_mode='oidc',oidc_config=self.config,
                oidc_subject_roles=(('analyst-sub','analyst'),)))
            with patch.object(app.state.store,'close',wraps=app.state.store.close) as close_store:
                with self.assertRaisesRegex(RuntimeError,'No demo connector'):
                    async with app.router.lifespan_context(app):
                        self.fail('Startup must fail')
                close_store.assert_called_once()
        stub.close.assert_awaited_once()

    async def test_reviewer_role_has_review_grants_without_execution_grants(self):
        from dataclasses import replace
        settings=replace(self.settings,oidc_subject_roles=(('reviewer-sub','reviewer'),))
        app=create_app(settings,self.gateway,verifier=self.verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            headers=self.headers('reviewer-sub',roles=['admin'])
            self.assertEqual((await client.get('/reviews',headers=headers)).status_code,200)
            self.assertEqual((await client.get('/responses',headers=headers)).status_code,200)
            self.assertEqual((await client.post('/investigations',json={'query':'PowerShell'},headers=headers)).status_code,403)

    async def test_case_directory_and_management_use_server_roles_not_jwt_claims(self):
        from dataclasses import replace
        settings=replace(self.settings,oidc_subject_roles=self.settings.oidc_subject_roles+(('reviewer-sub','reviewer'),))
        app=create_app(settings,self.gateway,verifier=self.verifier)
        identity=self.store.begin(TENANT,'analyst-sub')
        base='/investigations/'+identity+'/case'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            analyst=self.headers('analyst-sub',roles=['admin'],permissions=['cases:manage'],tenant='foreign')
            directory=await client.get('/case-assignees',headers=analyst)
            self.assertEqual(directory.json(),[{'subject':'admin-sub'},{'subject':'analyst-sub'}])
            me=(await client.get('/me',headers=analyst)).json()
            self.assertNotIn('cases:manage',me['permissions'])
            invalid=await client.post(base+'/assignment',headers=analyst,
                json={'expected_revision':0,'assignee':'reviewer-sub'})
            self.assertEqual(invalid.status_code,422)
            self.assertEqual((await client.post(base+'/assignment',headers=analyst,
                json={'expected_revision':0,'assignee':'admin-sub'})).status_code,200)
            self.assertEqual((await client.post(base+'/escalation',headers=analyst,
                json={'expected_revision':1,'reason':'Signed-token case escalation.'})).status_code,200)
            reviewer=self.headers('reviewer-sub',roles=['admin'])
            self.assertEqual((await client.get(base,headers=reviewer)).status_code,200)
            self.assertEqual((await client.get('/case-assignees',headers=reviewer)).status_code,403)
            self.assertEqual((await client.post(base+'/acknowledge',headers=reviewer,json={'expected_revision':2})).status_code,403)
            self.assertEqual((await client.post(base+'/acknowledge',headers=analyst,json={'expected_revision':2})).status_code,403)
            self.assertEqual((await client.post(base+'/acknowledge',headers=self.headers('admin-sub'),
                json={'expected_revision':2})).json()['escalation_state'],'acknowledged')

    async def test_removed_directory_subject_cannot_be_assigned_again(self):
        from dataclasses import replace
        identity=self.store.begin(TENANT,'analyst-sub')
        self.store.mutate_case(TENANT,'analyst-sub',identity,0,'assign',assignee='admin-sub')
        settings=replace(self.settings,oidc_subject_roles=(('analyst-sub','analyst'),))
        app=create_app(settings,self.gateway,verifier=self.verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            base='/investigations/'+identity+'/case'
            self.assertEqual((await client.get('/me',headers=self.headers('admin-sub'))).status_code,403)
            response=await client.post(base+'/assignment',headers=self.headers('analyst-sub'),
                json={'expected_revision':1,'assignee':'admin-sub'})
            self.assertEqual(response.status_code,422)
            cleared=await client.post(base+'/assignment',headers=self.headers('analyst-sub'),
                json={'expected_revision':1,'assignee':None})
            self.assertEqual(cleared.status_code,200,cleared.text)
            self.assertIsNone(cleared.json()['assignee'])

    async def test_incident_read_and_management_follow_trusted_roles(self):
        from dataclasses import replace
        settings=replace(self.settings,oidc_subject_roles=self.settings.oidc_subject_roles+(('reviewer-sub','reviewer'),))
        app=create_app(settings,self.gateway,verifier=self.verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            analyst=self.headers('analyst-sub',roles=['admin'],tenant='foreign',permissions=['cases:manage'])
            source=await client.post('/investigations',headers=analyst,json={'query':'PowerShell'})
            self.assertEqual(source.status_code,201,source.text)
            created=await client.post('/incidents',headers=analyst,json={'investigation_id':source.json()['id'],
                'title':'Signed-token incident','severity':'medium'})
            self.assertEqual(created.status_code,201,created.text)
            base='/incidents/'+created.json()['id']
            reviewer=self.headers('reviewer-sub',roles=['admin'])
            self.assertEqual((await client.get(base,headers=reviewer)).status_code,200)
            self.assertEqual((await client.get(base+'/activity',headers=reviewer)).status_code,200)
            self.assertEqual((await client.post(base+'/notes',headers=reviewer,
                json={'expected_revision':1,'body':'Read role cannot write notes.'})).status_code,403)
            self.assertEqual((await client.post(base+'/status',headers=analyst,
                json={'expected_revision':1,'status':'resolved','comment':'Analyst disposition.'})).status_code,200)
            self.assertEqual((await client.post(base+'/status',headers=analyst,
                json={'expected_revision':2,'status':'closed','comment':'Forged manager claim.'})).status_code,403)
            closed=await client.post(base+'/status',headers=self.headers('admin-sub'),
                json={'expected_revision':2,'status':'closed','comment':'Trusted manager disposition.'})
            self.assertEqual(closed.status_code,200,closed.text)
            self.assertEqual(closed.json()['closed_by'],'admin-sub')

    async def test_connector_review_enable_requires_trusted_admin_mapping(self):
        from dataclasses import replace
        settings=replace(self.settings,oidc_subject_roles=self.settings.oidc_subject_roles+(('reviewer-sub','reviewer'),))
        app=create_app(settings,self.gateway,verifier=self.verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            for subject in ('analyst-sub','reviewer-sub'):
                headers=self.headers(subject,roles=['admin'],permissions=['connectors:admin'])
                self.assertEqual((await client.get('/connectors/administration',headers=headers)).status_code,403)
                self.assertEqual((await client.post('/connectors/demo-rest/administration/disable',headers=headers,
                    json={'expected_revision':0,'reason':'Forged grant'})).status_code,403)
            headers=self.headers('admin-sub')
            state=(await client.get('/connectors/administration',headers=headers)).json()[0]
            self.assertEqual((await client.post('/connectors/demo-rest/administration/disable',headers=headers,
                json={'expected_revision':state['revision'],'reason':'Trusted administrator'})).status_code,200)
            body={'expected_revision':1,'manifest_hash':state['manifest_hash'],'reason':'Reviewed the registered read capability'}
            self.assertEqual((await client.post('/connectors/demo-rest/administration/review-enable',
                headers=self.headers('reviewer-sub',roles=['admin']),json=body)).status_code,403)
            enabled=await client.post('/connectors/demo-rest/administration/review-enable',headers=headers,json=body)
            self.assertEqual(enabled.status_code,200,enabled.text)
            self.assertEqual(enabled.json()['last_review']['actor'],'admin-sub')

    async def test_onboarding_uses_trusted_admin_mapping_and_signed_role_grants(self):
        from dataclasses import replace
        settings=replace(self.settings,oidc_subject_roles=(('analyst-sub','analyst'),('reviewer-sub','reviewer')))
        app=create_app(settings,self.gateway,verifier=self.verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            response=await client.get('/onboarding/status',headers=self.headers('reviewer-sub',roles=['admin'],permissions=['investigations:run']))
            self.assertEqual(response.status_code,200,response.text)
            data=response.json()
            self.assertEqual(data['authentication'],{'mode':'oidc','administrator_configured':False})
            self.assertFalse(data['can_investigate'])
            self.assertFalse(data['ready_for_investigation'])
            self.assertNotIn('reviewer-sub',response.text)
            self.assertNotIn(self.config.issuer,response.text)
            self.assertEqual((await client.get('/onboarding/status',headers=self.headers('unmapped',roles=['admin']))).status_code,403)
            analyst=(await client.get('/onboarding/status',headers=self.headers('analyst-sub'))).json()
            self.assertTrue(analyst['ready_for_investigation'])
            self.assertFalse(analyst['authentication']['administrator_configured'])
        original=await self.client.get('/onboarding/status',headers=self.headers())
        self.assertTrue(original.json()['authentication']['administrator_configured'])

    async def test_combined_incident_requires_every_source_scope_under_oidc(self):
        from dataclasses import replace
        settings=replace(self.settings,oidc_subject_roles=self.settings.oidc_subject_roles+(('reviewer-sub','reviewer'),))
        app=create_app(settings,self.gateway,verifier=self.verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://api') as client:
            analyst=self.headers('analyst-sub',roles=['admin'],permissions=['cases:manage'])
            primary=(await client.post('/investigations',headers=analyst,json={'query':'PowerShell'})).json()
            created=await client.post('/incidents',headers=analyst,
                json={'investigation_id':primary['id'],'title':'Joint source scope','severity':'medium'})
            self.assertEqual(created.status_code,201,created.text)
            base='/incidents/'+created.json()['id']
            other=self.store.begin(TENANT,'other-creator')
            self.store.finish(TENANT,'other-creator',other,{'synthetic':True,'evidence':[]},'completed')
            body={'expected_revision':1,'investigation_id':other,'comment':'Related synthetic source.'}
            self.assertEqual((await client.post(base+'/investigations',headers=analyst,json=body)).status_code,404)
            reviewer=self.headers('reviewer-sub',roles=['admin'])
            self.assertEqual((await client.post(base+'/investigations',headers=reviewer,json=body)).status_code,403)
            linked=await client.post(base+'/investigations',headers=self.headers('admin-sub'),json=body)
            self.assertEqual(linked.status_code,200,linked.text)
            self.assertEqual((await client.get(base,headers=analyst)).status_code,404)
            self.assertEqual((await client.get('/incidents',headers=analyst)).json(),[])
            sources=await client.get(base+'/investigations',headers=reviewer)
            self.assertEqual(sources.status_code,200,sources.text)
            self.assertEqual({source['investigation_id'] for source in sources.json()},{primary['id'],other})
