"""Scope presentation follows the real supported category set without widening enforcement."""
from pathlib import Path
import unittest
from unittest.mock import patch

from agent_platform import masking_scope
from runtime.phase3.trusted_runtime import SUPPORTED_ENTITIES
from test_console import make

ROOT=Path(__file__).resolve().parents[3]


class Scope(unittest.TestCase):
    def test_exact_supported_categories_and_explicit_exclusions(self):
        value=masking_scope.scope()
        self.assertEqual({row['code'] for row in value['supported']},SUPPORTED_ENTITIES)
        self.assertEqual(value['not_masked'],['person names','passport numbers'])
        self.assertIn('Person names and passport numbers are not masked.',value['summary'])
        self.assertIn('format and context',value['limits'])
        self.assertIn('without a named category',value['additional'])

    def test_a_new_category_cannot_silently_keep_stale_scope_wording(self):
        with patch.object(masking_scope,'SUPPORTED_ENTITIES',SUPPORTED_ENTITIES|{'NEW_CATEGORY'}):
            with self.assertRaises(ValueError): masking_scope.scope()

    def test_every_relevant_console_explanation_uses_the_same_scope(self):
        console=make({})
        for topic in ('redactor','gateway-boundary'):
            result=console.explain(topic)
            words=result['plain']+' '+result['how']
            self.assertIn(masking_scope.SUMMARY,words)
            for row in masking_scope.scope()['supported']:
                self.assertIn(row['label'],words)
        self.assertIn('not prove complete or authentic audit',console.explain('audit')['how'])

    def test_financial_image_packages_the_shared_scope_module(self):
        path='platform/core/src/agent_platform/masking_scope.py'
        self.assertIn(path,(ROOT/'platform/agents/financial/Dockerfile').read_text())
        self.assertIn('!'+path,(ROOT/'platform/agents/financial/Dockerfile.dockerignore').read_text())


class CurrentFrontdoorProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        from unittest.mock import Mock
        from finance_agent.auth import Sessions, LoginThrottle, hash_password
        from finance_agent.frontdoor import Forwarder
        from finance_agent.server import Handler, Server
        from agent_platform.data_capability import CapabilityIssuer
        from agent_platform.ops.approval import generate_keypair
        cls.account={'id':'00000000-0000-4000-8000-000000000001','display_name':'Demo',
                     'password_hash':hash_password('synthetic-password')}
        class Users:
            def user(self,name): return cls.account if name=='demo' else None
        private,public=generate_keypair()
        cls.dispatch=Mock(side_effect=AssertionError('profile must not call a worker or model'))
        cls.http=Server(('127.0.0.1',0),Handler)
        cls.http.hosts={f'127.0.0.1:{cls.http.server_port}'}
        cls.http.store,cls.http.sessions,cls.http.throttle=Users(),Sessions(b'x'*32),LoginThrottle()
        cls.http.agent=Forwarder(CapabilityIssuer(private,public),{
            cls.account['id']:{'agent':'worker','key':'a'*64,'url':'http://127.0.0.1:1/ask'}},dispatch=cls.dispatch)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join(3)

    def call(self,method,path,body=None,cookie=None):
        import http.client
        import json
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        headers={'Origin':f'http://127.0.0.1:{self.http.server_port}'}
        if body is not None: headers['Content-Type']='application/json'
        if cookie: headers['Cookie']=cookie
        connection.request(method,path,body=None if body is None else json.dumps(body),headers=headers)
        response=connection.getresponse()
        result=response.status,json.loads(response.read()),response.getheader('Set-Cookie')
        connection.close()
        return result

    def test_login_and_reloaded_profile_share_the_same_real_masking_scope(self):
        status,login,cookie=self.call('POST','/api/login',{'username':'demo','password':'synthetic-password'})
        self.assertEqual(status,200)
        self.assertIn('HttpOnly',cookie)
        self.assertEqual(login['masking_scope'],masking_scope.scope())
        status,profile,_=self.call('GET','/api/me',cookie=cookie.split(';')[0])
        self.assertEqual(status,200)
        self.assertEqual(profile['masking_scope'],login['masking_scope'])
        self.assertEqual(profile['name'],'Demo')
        self.dispatch.assert_not_called()

    def test_profile_remains_authenticated(self):
        self.assertEqual(self.call('GET','/api/me')[0],401)


if __name__=='__main__': unittest.main()
