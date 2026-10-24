"""F1–F4 focused protocol/config tests. Real local HTTP/crypto/SQLite; provider and Kubernetes API are fixtures."""
import contextlib
import copy
import datetime
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

import yaml
from agent_platform.boundary_http import Rejected, Server
from agent_platform.data_capability import CapabilityIssuer
from agent_platform.gateway_boundary import GatewayBoundary
from agent_platform.ops import approval, diagnose
from agent_platform.ops.agent import Agent
from agent_platform.ops.executor import Executor, ExecutorClient, ReplayStore
from agent_platform import onboarding, platform_secrets
from finance_agent.agent import FinanceAgent
from finance_agent.data_broker import DataBroker, RemoteStore
from finance_agent.frontdoor import Forwarder
from finance_agent.worker import Worker
from runtime.phase3.trusted_runtime import RedactionResult
from fixtures import FakeClient, REGISTRY, deployment, pod

ROOT = Path(__file__).resolve().parents[3]
ALICE, BOB = '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002'


class Masker:
    def __init__(self, fail=False): self.fail, self.calls = fail, []
    def redact(self, text):
        self.calls.append(text)
        if self.fail: raise RuntimeError('synthetic outage')
        return RedactionResult(text.replace('alice@example.invalid', '[EMAIL_ADDRESS]'), ())


class GatewayF1(unittest.TestCase):
    def boundary(self, fail=False):
        self.receipts, self.masker = [], Masker(fail)
        def provider(url, key, body, **kwargs):
            self.receipts.append((url, key, copy.deepcopy(body)))
            return {'choices': []}, {}
        return GatewayBoundary({'agent-financial': {'external_key': 'e'*64, 'upstream_key': 'p'*64}},
                               self.masker, dispatch=provider)

    def body(self):
        return {'model': 'secure-financial-chat', 'max_tokens': 512, 'stream': False,
                'response_format': {'type': 'json_object'},
                'messages': [{'role': 'system', 'content': 'synthetic rules'},
                             {'role': 'user', 'content': 'alice@example.invalid'}]}

    def test_direct_valid_agent_http_key_cannot_skip_server_redaction(self):
        boundary = self.boundary()
        server = Server(('127.0.0.1', 0), boundary)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
            conn.request('POST', '/v1/chat/completions', json.dumps(self.body()),
                         {'Authorization': 'Bearer '+'e'*64, 'Content-Type': 'application/json'})
            response = conn.getresponse();response.read();self.assertEqual(response.status, 200);conn.close()
            self.assertEqual(len(self.masker.calls), 2)
            self.assertNotIn('alice@example.invalid', json.dumps(self.receipts))
            self.assertEqual(self.receipts[0][1], 'p'*64)
        finally:
            server.shutdown();server.server_close();thread.join(3)

    def test_redactor_failure_prevents_provider_dispatch(self):
        boundary = self.boundary(True)
        with self.assertRaises(Rejected): boundary.handle('/v1/chat/completions', 'Bearer '+'e'*64, self.body())
        self.assertEqual(self.receipts, [])

    def test_existing_ops_explanation_has_only_its_fixed_bounded_timeout(self):
        boundary=self.boundary()
        boundary.clients=type(boundary.clients)({'ops-explain':'e'*64})
        boundary.upstream={'ops-explain':'p'*64}
        boundary.handle('/v1/chat/completions','Bearer '+'e'*64,dict(self.body(),timeout=20))
        self.assertEqual(len(self.receipts),1)
        with self.assertRaises(Rejected):
            boundary.handle('/v1/chat/completions','Bearer '+'e'*64,dict(self.body(),timeout=300))

    def test_unknown_keys_routes_streams_and_provider_overrides_reject(self):
        for path, key, extra in [('/key/generate','e'*64,{}),('/v1/chat/completions','p'*64,{}),
                                  ('/v1/chat/completions','e'*64,{'api_base':'http://untrusted.invalid'}),
                                  ('/v1/chat/completions','e'*64,{'stream':True}),
                                  ('/v1/chat/completions','e'*64,{'timeout':20})]:
            with self.subTest(path=path, extra=list(extra)):
                boundary = self.boundary()
                with self.assertRaises(Rejected):boundary.handle(path, 'Bearer '+key, dict(self.body(), **extra))
                self.assertEqual(self.receipts, [])


class ReadStore:
    def __init__(self): self.users=[]
    def read(self, user, statement, params):
        self.users.append(user)
        return [(2450 if user == ALICE else 990000, 1)]


class DataF2F3(unittest.TestCase):
    def setUp(self):
        self.private, self.public = approval.generate_keypair()
        self.issuer = CapabilityIssuer(self.private, self.public)
        self.store = ReadStore()
        self.broker = DataBroker(self.store, self.issuer, {'financial':'b'*64, 'other':'o'*64}, user_bindings={'financial':ALICE, 'other':BOB}, audit_key=b'a'*32)
        self.token, self.claims = self.issuer.issue(ALICE, 'financial')
        self.body = {'capability':self.token, 'tool':'monthly_total', 'args':{'month':'2026-10'}}

    def test_broker_binds_sql_identity_to_verified_frontdoor_capability(self):
        result, _ = self.broker.handle('/tools','Bearer '+'b'*64,self.body)
        self.assertEqual(result['total_minor'],2450)
        self.assertEqual(self.store.users,[ALICE])

    def test_forged_user_wrong_agent_revoked_token_or_sql_override_cannot_query(self):
        forged = self.token.split('.')
        from agent_platform.data_capability import unb64,b64
        claims=json.loads(unb64(forged[0]));claims['user']=BOB
        forged_token=b64(json.dumps(claims).encode())+'.'+forged[1]
        for key, body in [('b'*64,dict(self.body,capability=forged_token)),('o'*64,self.body),
                          ('b'*64,dict(self.body,user_id=BOB)),('b'*64,dict(self.body,sql='SELECT * FROM finance.users')),
                          ('b'*64,dict(self.body,args={'month':'2026-10','user_id':BOB}))]:
            with self.subTest(extra=list(body)),self.assertRaises(Rejected):self.broker.handle('/tools','Bearer '+key,body)
        self.issuer.revoke(self.claims)
        with self.assertRaises(Rejected):self.broker.handle('/tools','Bearer '+'b'*64,self.body)
        self.assertEqual(self.store.users,[])

    def test_even_genuine_foreign_user_capability_cannot_cross_fixed_worker_binding(self):
        token, _ = self.issuer.issue(BOB, 'financial')
        with self.assertRaises(Rejected):
            self.broker.handle('/tools', 'Bearer '+'b'*64, dict(self.body, capability=token))
        self.assertEqual(self.store.users, [])

    def test_unmapped_authenticated_user_gets_no_worker_or_capability(self):
        receipts=[]
        front=Forwarder(self.issuer, {ALICE:{'agent':'financial','key':'w'*64,'url':'http://127.0.0.1/ask'}},
                        dispatch=lambda *a, **kw:receipts.append(a))
        result=front.ask(BOB,'Synthetic question','en')
        self.assertEqual(result['status'],'blocked');self.assertEqual(receipts,[])
        self.assertEqual(len(self.issuer.active),1)

    def test_frontdoor_worker_broker_legitimate_flow_and_turn_revocation(self):
        broker=self.broker
        remote=RemoteStore('b'*64,dispatch=lambda url,key,body:broker.handle('/tools','Bearer '+key,body))
        class Model:
            def __init__(self):self.calls=0
            def complete(self, messages):
                self.calls+=1
                return json.dumps({'action':'tool','tool':'monthly_total','args':{'month':'2026-10'}} if self.calls==1
                                  else {'action':'answer','text':'You spent 24.50 SAR.'}),10
        agent=FinanceAgent(remote,Masker(),Model(),audit_key=b'x'*32)
        worker=Worker('financial','w'*64,self.public,agent,remote,user_id=ALICE)
        front=Forwarder(self.issuer,{ALICE:{'agent':'financial','key':'w'*64,'url':'http://127.0.0.1/ask'}},
                        dispatch=lambda url,key,body,**kw:worker.handle('/ask','Bearer '+key,body))
        result=front.ask(ALICE,'Summarize synthetic expenses.','en')
        self.assertEqual(result['status'],'answered');self.assertEqual(self.store.users,[ALICE])
        self.assertEqual(len(self.issuer.active),1)  # only setUp's unrelated live token remains

    def test_forget_uses_the_authenticated_users_separate_worker(self):
        remote=RemoteStore('b'*64)
        class Memory:
            def __init__(self):self.forgot=[]
            def forget(self,user):self.forgot.append(user)
        agent=Memory();worker=Worker('financial','w'*64,self.public,agent,remote,user_id=ALICE)
        front=Forwarder(self.issuer,{ALICE:{'agent':'financial','key':'w'*64,'url':'http://127.0.0.1/ask'}},
                        dispatch=lambda url,key,body:worker.handle('/forget','Bearer '+key,body))
        front.forget(ALICE);self.assertEqual(agent.forgot,[ALICE]);self.assertEqual(len(self.issuer.active),1)

    def test_existing_user_directory_preserves_identity_without_resetting_passwords(self):
        from unittest.mock import Mock
        hasher=Mock(side_effect=AssertionError('must not generate existing-user password hashes'))
        directory={name:str(__import__('uuid').uuid4()) for name,_ in platform_secrets.FINANCE_USERS}
        config,passwords=platform_secrets.finance_config(hasher,user_directory=directory)
        self.assertEqual(passwords,{})
        self.assertTrue(config['preserve_existing_users'])
        self.assertEqual({u['username']:u['id'] for u in config['users']},directory)
        self.assertTrue(all(u['password_hash'] is None for u in config['users']));hasher.assert_not_called()

    def test_existing_user_directory_rejects_missing_or_shared_identity(self):
        for directory in ({'lama':ALICE},{name:ALICE for name,_ in platform_secrets.FINANCE_USERS}):
            with self.subTest(directory_size=len(directory)),self.assertRaises(ValueError):
                platform_secrets.finance_config(user_directory=directory)

    def test_worker_secret_has_no_database_session_or_signer_material(self):
        items=platform_secrets.generate('synthetic-owner-passphrase',hasher=lambda users:{u:'$argon2id$synthetic' for u in users})
        import base64
        data={d['metadata']['namespace']+'/'+d['metadata']['name']:{k:base64.b64decode(v).decode() for k,v in d['data'].items()} for d in items}
        workers=[json.loads(data['agent-financial/agent-'+slot]['agent.json']) for slot in onboarding.USER_SLOTS]
        self.assertEqual(len({v['broker_key'] for v in workers}),3)
        self.assertEqual(len({v['user_id'] for v in workers}),3)
        worker=workers[0]
        self.assertEqual(set(worker),{'gateway_key','redactor_key','agent_name','broker_key','worker_key','capability_public_key','user_id'})
        self.assertNotIn('postgresql://',json.dumps(worker));self.assertNotIn('PRIVATE KEY',json.dumps(worker))
        boundary=json.loads(data['platform/gateway-boundary']['boundary.json'])
        self.assertTrue(all(c['external_key']!=c['upstream_key'] for c in boundary['clients'].values()))
        self.assertNotIn('approver_private_key',json.loads(data['ops/ops-executor']['executor.json']))


class OpsF4(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.private,self.public=approval.generate_keypair()
        def apply(d,p):
            d=copy.deepcopy(d);d['spec']['replicas']=p['spec'].get('replicas',1)
            d['metadata']['generation']+=1
            d['status'].update(observedGeneration=d['metadata']['generation'],replicas=2,updatedReplicas=2,availableReplicas=2)
            return d
        self.client=FakeClient(deployment(available=0),pods=[pod(ready=False)],after_patch=apply)
        self.path=Path(self.temp.name)/'nonces.sqlite'
        self.executor=Executor(self.client,{'apps.fault-demo':REGISTRY['apps.fault-demo']},self.public,'e'*64,
                               replay_store=ReplayStore(self.path),verify_kwargs={'timeout':.05,'interval':.001})
        reader=FakeClient(deployment(available=0),pods=[pod(ready=False)])
        self.agent=Agent(reader,{'apps.fault-demo':REGISTRY['apps.fault-demo']},approval.Verifier(self.public),
                         executor=ExecutorClient('e'*64,dispatch=lambda url,key,body,**kw:self.executor.handle('/execute','Bearer '+key,body)))
        f=diagnose.diagnose(reader.deployment,reader.pods,[])
        self.proposal=self.agent.propose('apps.fault-demo','scale',{'replicas':2},f)

    def test_valid_owner_approval_uses_independent_executor_only(self):
        result=self.agent.execute(self.proposal['request_id'],approval.Signer(self.private).sign(self.proposal))
        self.assertEqual(result['result'],'VERIFIED')
        self.assertEqual(self.agent.client.patches,[]);self.assertEqual(len(self.client.patches),1)

    def test_compromised_ops_with_broker_key_cannot_self_authorize_or_change_arguments(self):
        other,_=approval.generate_keypair()
        signed=approval.Signer(self.private).sign(self.proposal)
        forged=approval.Signer(other).sign(self.proposal)
        changed=copy.deepcopy(self.proposal);changed['arguments']={'replicas':3}
        for proposal,token in [(self.proposal,''),(self.proposal,forged),(changed,signed)]:
            with self.subTest(token_present=bool(token)),self.assertRaises(Rejected):
                self.executor.handle('/execute','Bearer '+'e'*64,{'proposal':proposal,'approval':token})
        self.assertEqual(self.client.patches,[])

    def test_replay_storage_failure_prevents_any_patch(self):
        self.executor.agent.verifier._nonce_store = type('Unavailable', (), {'consume':lambda *a:(_ for _ in ()).throw(OSError('synthetic outage'))})()
        result, _ = self.executor.handle('/execute','Bearer '+'e'*64,{'proposal':self.proposal,'approval':approval.Signer(self.private).sign(self.proposal)})
        self.assertEqual(result['code'],'APPROVAL_STORAGE_UNAVAILABLE');self.assertEqual(self.client.patches,[])

    def test_replay_store_survives_executor_recreation(self):
        token=approval.Signer(self.private).sign(self.proposal)
        self.executor.handle('/execute','Bearer '+'e'*64,{'proposal':self.proposal,'approval':token})
        self.assertFalse(ReplayStore(self.path).consume(self.proposal['request_id']))
        # Fresh executor keeps the same durable nonce store, even within the original issuance second.
        second=Executor(self.client,self.executor.agent.targets,self.public,'e'*64,replay_store=ReplayStore(self.path))
        try:result,_=second.handle('/execute','Bearer '+'e'*64,{'proposal':self.proposal,'approval':token})
        except Rejected:result={'result':'DENIED'}
        self.assertEqual(result['result'],'DENIED');self.assertEqual(len(self.client.patches),1)


class DeploymentContracts(unittest.TestCase):
    def test_historical_image_lock_cannot_deploy_new_boundary_contract(self):
        import importlib.util
        from types import SimpleNamespace
        path = ROOT/'platform/clouds/gke/render.py'
        spec = importlib.util.spec_from_file_location('boundary_render', path)
        render = importlib.util.module_from_spec(spec);spec.loader.exec_module(render)
        for lock in (None, str(ROOT/'platform/clouds/gke/images.json')):
            with self.subTest(lock_present=lock is not None), self.assertRaises(render.Rejected):
                render.render(SimpleNamespace(images_lock=lock))

    def test_per_user_workloads_have_disjoint_selectors_secrets_and_bounded_quota(self):
        docs=onboarding.render_agent(onboarding.load_all()['financial'])
        workers=[d for d in docs if d['kind']=='Deployment']
        self.assertEqual(len(workers),3)
        for worker in workers:
            name=worker['metadata']['name'];pod=worker['spec']['template']
            self.assertEqual(pod['spec']['volumes'][0]['secret']['secretName'],name)
            self.assertEqual(worker['spec']['selector']['matchLabels']['agent-platform/user-slot'],name.removeprefix('agent-'))
            self.assertFalse(pod['spec']['automountServiceAccountToken'])
        quota=next(d for d in docs if d['kind']=='ResourceQuota')['spec']['hard']
        self.assertEqual(quota['pods'],'4')

    def test_legacy_up_fails_before_any_cloud_or_cluster_call(self):
        import importlib.util
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('boundary_lifecycle',ROOT/'platform/clouds/gke/lifecycle.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module,'run') as run, patch.object(module,'resize') as resize:
            with self.assertRaisesRegex(SystemExit,'reviewed_v2_cutover_bundle_required'):module.up()
            run.assert_not_called();resize.assert_not_called()

    def test_ops_identity_has_no_mutation_grants(self):
        docs=list(yaml.safe_load_all((ROOT/'platform/core/kubernetes/policies/ops-agent-rbac.yaml').read_text()))
        roles={(d['metadata']['namespace'],d['metadata']['name']):d for d in docs if d['kind']=='Role'}
        def verbs(subject):
            return {v for d in docs if d['kind']=='RoleBinding' and any(s['name']==subject for s in d['subjects'])
                    for rule in roles[(d['metadata']['namespace'],d['roleRef']['name'])]['rules'] for v in rule['verbs']}
        self.assertLessEqual(verbs('ops-agent'),{'get','list','watch'})
        self.assertIn('patch',verbs('ops-executor'))

    def test_agents_have_no_direct_sql_or_private_provider_path(self):
        for m in onboarding.load_all().values():
            rules=onboarding.egress(m)
            ports={p['port'] for r in rules for p in r['ports']}
            self.assertFalse(ports & {5432,4001})
            self.assertIn(4000,ports)
        policies=list(yaml.safe_load_all((ROOT/'platform/core/kubernetes/policies/admission.yaml').read_text()))
        self.assertIn("== 'system:serviceaccount:ops:ops-executor'",policies[0]['spec']['validations'][0]['expression'])


class FinancialImageInputs(unittest.TestCase):
    def test_copied_platform_modules_are_in_the_build_context(self):
        dockerfile = (ROOT / 'platform/agents/financial/Dockerfile').read_text()
        allowlist = (ROOT / 'platform/agents/financial/Dockerfile.dockerignore').read_text().splitlines()
        for line in dockerfile.splitlines():
            if line.startswith('COPY ') and '/agent_platform/' in line:
                for source in line.split()[2:-1]:
                    with self.subTest(source=source):
                        self.assertIn('!' + source, allowlist)
                        self.assertTrue((ROOT / source).is_file())
