"""The current rendered matrix, transactional faults/fixtures and the complete recording command."""
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'platform/clouds/gke'))
import attack_suite
import attack_network
from attack_runner import Case, run, safe_evidence
from attack_runtime import NotExercised, RestoreFailed, temporary_fault, temporary_annotation
from test_release_facts import ReleaseFacts


class Matrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,_=ReleaseFacts().selected()

    def test_contract_uses_every_current_worker_and_the_two_trusted_mediators(self):
        targets,matrix,metadata=attack_network.inventory(self.docs)
        workers=[(s,w) for s,w in matrix if s[0]=='agent-financial']
        self.assertEqual({s[1] for s,_ in workers},{'agent-u1','agent-u2','agent-u3'})
        for _,wanted in workers:
            self.assertEqual({k for k,v in wanted.items() if v=='CONNECTED'},{'boundary','redactor','broker'})
            self.assertEqual((wanted['database'],wanted['provider'],wanted['executor']),('DENIED',)*3)
        self.assertTrue(any(s[:2]==('ops','ops-executor') for s,_ in matrix))
        self.assertEqual(metadata[:2],('platform','redactor'))
        self.assertEqual(metadata[4],'/usr/local/bin/python3.12')
        self.assertEqual({source[3:5] for source, _ in matrix},
                         {('python', '/usr/local/bin/python3.12'), ('node', '/nodejs/bin/node')})
        redactor = next(d for d in self.docs if d.get('kind') == 'Deployment'
                        and (d['metadata']['namespace'], d['metadata']['name'])
                        == ('platform', 'redactor'))
        self.assertNotIn('command', redactor['spec']['template']['spec']['containers'][0])

    def fake(self, *, bad=None):
        targets,matrix,_=attack_network.inventory(self.docs)
        expected={(s[0],s[1]):wanted for s,wanted in matrix}
        def execute(namespace,name,code,container,**kwargs):
            # Read the explicit target names from the generated program, not its production allow rules.
            if code.startswith('const'):
                raw=code.split(' T=',1)[1].split(';',1)[0]
                endpoints=json.loads(raw)
            else:
                raw=code.split(' in ',1)[1].split(':\n',1)[0]
                endpoints=json.loads(raw)
            wanted=expected.get((namespace,name),{})
            values={label:wanted.get(label,'CONNECTED') for label,_,_ in endpoints}
            if (namespace,name)==('agent-platform-guide','agent') and 'guide' in values: values['guide']='CONNECTED'
            if bad: bad(namespace,name,values)
            return SimpleNamespace(returncode=0,stdout=json.dumps(values))
        return execute

    def test_current_matrix_needs_positive_controls_and_rejects_unexpected_reachability(self):
        fake=self.fake()
        self.assertTrue(attack_network.check(self.docs,fake,fake,external_control=lambda:True)[0])
        def open_database(namespace,name,values):
            if namespace=='agent-financial' and 'database' in values: values['database']='CONNECTED'
        fake=self.fake(bad=open_database)
        self.assertFalse(attack_network.check(self.docs,fake,fake,external_control=lambda:True)[0])

    def test_dns_refused_targets_and_unavailable_controls_cannot_prove_denial(self):
        for outcome in ('DNS_ERROR','TARGET_ERROR'):
            def broken(namespace,name,values):
                if namespace=='agent-financial' and 'database' in values: values['database']=outcome
            fake=self.fake(bad=broken)
            with self.assertRaises(NotExercised): attack_network.check(self.docs,fake,fake,external_control=lambda:True)
        fake=self.fake()
        with self.assertRaises(NotExercised): attack_network.check(self.docs,fake,fake,external_control=lambda:False)

    def test_probe_programs_distinguish_refused_and_dns_errors_in_both_runtimes(self):
        # Inject only the transport primitive; run the actual generated Python/Node classification logic.
        python="""import socket,errno
def connect(target,**kwargs):
 if target[0]=='dns': raise socket.gaierror(-2,'synthetic')
 if target[0]=='refused': raise ConnectionRefusedError(errno.ECONNREFUSED,'synthetic')
 raise TimeoutError('synthetic')
socket.create_connection=connect
"""+attack_network.PYTHON.replace('TARGETS',json.dumps([['dns','dns',1],['refused','refused',1],['denied','denied',1]]))
        result=subprocess.run([sys.executable,'-c',python],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(result.stdout),{'dns':'DNS_ERROR','refused':'TARGET_ERROR','denied':'DENIED'})
        javascript="""const real=require;const events=real('node:events');const mocked={connect:({host})=>{
const s=new events.EventEmitter();s.destroy=()=>{};s.setTimeout=(n,f)=>{if(host==='denied')queueMicrotask(f);};
queueMicrotask(()=>{if(host!=='denied')s.emit('error',{code:host==='dns'?'ENOTFOUND':'ECONNREFUSED'});});return s;}};
require=(name)=>name==='node:net'?mocked:real(name);
"""+attack_network.NODE.replace('TARGETS',json.dumps([['dns','dns',1],['refused','refused',1],['denied','denied',1]]))
        result=subprocess.run(['node','-e',javascript],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(result.stdout),{'dns':'DNS_ERROR','refused':'TARGET_ERROR','denied':'DENIED'})


class JsonKube:
    def __init__(self):
        self.doc={'metadata':{'uid':'original','resourceVersion':'1','annotations':{'attack-suite/touched':'before','keep':'yes'}},
            'spec':{'replicas':0,'template':{'metadata':{'labels':{'app':'fault-demo'}},
                'spec':{'containers':[{'name':'workload','image':'signed','env':[{'name':'PYTHONPATH','value':'original'}]}]}}}}
        self.calls=[]
    def __call__(self,*args,**kwargs):
        self.calls.append(args)
        if 'get' in args: return SimpleNamespace(returncode=0,stdout=json.dumps(self.doc))
        if 'patch' in args:
            changed=deepcopy(self.doc)
            for op in json.loads(args[args.index('-p')+1]):
                parts=[p.replace('~1','/').replace('~0','~') for p in op['path'].strip('/').split('/')]
                parent=changed
                for part in parts[:-1]: parent=parent[part]
                key=parts[-1]
                if op['op']=='test' and parent.get(key)!=op['value']: return SimpleNamespace(returncode=1)
                if op['op'] in ('replace','add'): parent[key]=op['value']
                if op['op']=='remove': del parent[key]
            self.doc=changed;self.doc['metadata']['resourceVersion']=str(int(self.doc['metadata']['resourceVersion'])+1)
        return SimpleNamespace(returncode=0,stdout='')


class FaultCleanup(unittest.TestCase):
    def test_both_fault_modes_restore_original_template_and_stopped_state(self):
        for mode in ('wedge','inject'):
            kube=JsonKube();original=deepcopy(kube.doc['spec'])
            try:
                with temporary_fault(kube,mode):
                    self.assertEqual(kube.doc['spec']['replicas'],1)
                    kube.doc['spec']['template']['metadata']['annotations']={'kubectl.kubernetes.io/restartedAt':'approved-restart'}
                    raise NotExercised('synthetic')
            except NotExercised: pass
            self.assertEqual(kube.doc['spec'],original)

    def test_fault_cleanup_never_discards_another_owner_template_edit(self):
        kube=JsonKube()
        with self.assertRaises(RestoreFailed):
            with temporary_fault(kube,'inject'):
                kube.doc['spec']['template']['metadata']['labels']['operator']='preserve'
        self.assertEqual(kube.doc['spec']['template']['metadata']['labels']['operator'],'preserve')

    def test_metadata_probe_restores_preexisting_field_and_preserves_unrelated_changes(self):
        kube=JsonKube()
        with temporary_annotation(kube): kube.doc['metadata']['annotations']['other-owner']='preserve'
        self.assertEqual(kube.doc['metadata']['annotations'],{'attack-suite/touched':'before','keep':'yes','other-owner':'preserve'})

    def test_metadata_probe_refuses_to_overwrite_same_field_changed_by_another_owner(self):
        kube=JsonKube()
        with self.assertRaises(RestoreFailed):
            with temporary_annotation(kube): kube.doc['metadata']['annotations']['attack-suite/touched']='operator-value'
        self.assertEqual(kube.doc['metadata']['annotations']['attack-suite/touched'],'operator-value')


class Orchestration(unittest.TestCase):
    def test_unavailable_setup_never_becomes_a_pass_and_cleanup_always_runs(self):
        called=[]
        def unavailable(): raise NotExercised('synthetic')
        rows=run([Case('setup_case','control',unavailable),Case('attack_case','attack',lambda:(True,{}),('setup_case',)),
            Case('owned_cleanup','control',lambda:(called.append(True) or True,{}),always=True)],emit=lambda _:None)
        self.assertEqual([r['verdict'] for r in rows],['NOT_EXERCISED','NOT_EXERCISED','PASS'])
        self.assertEqual(called,[True])

    def test_cleanup_failure_stops_later_attacks_but_runs_remaining_cleanup(self):
        called=[]
        def failed(): raise RestoreFailed('synthetic')
        rows=run([Case('cleanup_case','control',failed,always=True),Case('attack_case','attack',lambda:(called.append('unsafe') or True,{})),
            Case('transport_cleanup','control',lambda:(called.append('closed') or True,{}),always=True)],emit=lambda _:None)
        self.assertEqual(called,['closed'])
        self.assertEqual([r['verdict'] for r in rows],['FAIL','NOT_EXERCISED','PASS'])

    def test_unsafe_evidence_never_reaches_output_or_a_success_certificate(self):
        for value in ('private-project-fixture',123456789012,'sk-'+'z'*40):
            output=[]
            rows=run([Case('attack_case','attack',lambda:(True,{'payload':value}))],
                private=('private-project-fixture',123456789012),emit=output.append)
            self.assertNotEqual(rows[0]['verdict'],'PASS')
            self.assertNotIn(str(value),json.dumps(rows)+json.dumps(output))

    def test_incomplete_nested_control_is_not_a_pass(self):
        rows=run([Case('attack_case','attack',lambda:(True,{'workers':[{'verdict':'NOT_EXERCISED'}]}))],emit=lambda _:None)
        self.assertEqual(rows[0]['verdict'],'NOT_EXERCISED')

    def test_main_writes_a_fresh_incomplete_report_and_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json';path.write_text('{"stale_success":true}')
            def unavailable(): raise NotExercised('synthetic')
            with patch.object(attack_suite.lifecycle,'settings',return_value={'project_id':'private-project-fixture'}), \
                    patch.object(attack_suite,'build_cases',return_value=[Case('attack_case','attack',unavailable)]), \
                    patch.object(attack_suite,'publish',return_value=False), patch('sys.stdout',new_callable=io.StringIO) as output:
                with self.assertRaises(SystemExit) as exit: attack_suite.main(['--out',str(path)])
                self.assertEqual(exit.exception.code,1)
            data=json.loads(path.read_text())
            self.assertNotIn('stale_success',data)
            self.assertEqual(data['results'][0]['verdict'],'NOT_EXERCISED')
            self.assertFalse(data['published'])
            self.assertNotIn('private-project-fixture',output.getvalue()+path.read_text())

    def test_controlled_exit_and_interrupt_still_write_verdicts_and_run_cleanup(self):
        for exception in (SystemExit(3),KeyboardInterrupt()):
            calls=[]
            def stopped(): raise exception
            rows=run([Case('attack_case','attack',stopped),Case('owned_cleanup','control',lambda:(calls.append(True) or True,{}),always=True)],emit=lambda _:None)
            self.assertNotEqual(rows[0]['verdict'],'PASS')
            self.assertEqual(calls,[True])

    def test_known_breach_is_not_hidden_by_another_unavailable_control(self):
        rows=run([Case('attack_case','attack',lambda:(True,{'parts':[{'verdict':'FAIL'},{'verdict':'NOT_EXERCISED'}]}))],emit=lambda _:None)
        self.assertEqual(rows[0]['verdict'],'FAIL')

    def test_synthetic_fixture_entries_match_the_current_input_contract_and_evade_only_the_intended_filter(self):
        from finance_agent.store import validate_expense
        from finance_agent.tools import instruction_like
        from attack_fixture_spec import MONTH,ENTRIES,INJECTION_MERCHANT
        for _,day,merchant,category,amount in ENTRIES:
            validate_expense({'spent_on':MONTH+'-'+day,'merchant':merchant,'category':category,'amount':amount,'note':'synthetic-fixture'})
        self.assertFalse(instruction_like(INJECTION_MERCHANT))

    def test_digit_merchant_positive_control_requires_its_actual_amount_and_name(self):
        class App:
            def __init__(self,text): self.text=text
            def ask(self,*args): return {'status':'answered','answer':self.text}
        for text,expected in (('7-Eleven: 15.00 SAR',True),('7-Eleven: 1.00 SAR',False),('15.00 SAR',False)):
            self.assertEqual(attack_suite.case_merchant_with_digits(App(text),('cookie','csrf'))[0],expected)

    def test_executor_http_refusal_is_distinct_from_infrastructure_failure(self):
        envelope={'status':403,'body':{'code':'APPROVAL_REJECTED'}}
        with patch.object(attack_suite,'exec_python',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(envelope))) as execute:
            self.assertEqual(attack_suite.ops_execute({'test':'proposal'},'',forge=True),{'result':'DENIED','code':'APPROVAL_REJECTED'})
            self.assertEqual(execute.call_args.args[:2],('ops','ops-agent'))
            self.assertTrue(json.loads(execute.call_args.kwargs['input'])['forge'])
        envelope['status']=503
        with patch.object(attack_suite,'exec_python',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(envelope))):
            with self.assertRaises(NotExercised): attack_suite.ops_execute({},'')

    def test_cross_user_mutation_is_owned_before_send_even_when_the_reply_is_lost(self):
        import base64
        from attack_fixtures import FixtureRows
        users=('00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002')
        sessions=[('fa_session='+base64.urlsafe_b64encode(json.dumps({'u':u}).encode()).rstrip(b'=').decode()+'.signature','csrf') for u in users]
        fixture=FixtureRows(None,None)
        class LostResponse:
            def call(inner,method,path,entry,*session):
                self.assertEqual({r['user'] for r in fixture.rows},set(users))
                self.assertEqual(entry['user_id'],users[1])
                self.assertEqual(entry['note'],fixture.tag)
                raise ConnectionError('synthetic lost response after commit')
        fixture.app=LostResponse()
        with self.assertRaises(ConnectionError): fixture.attempt_cross_user_insert(*sessions)
        self.assertEqual(len(fixture.rows),2)
        self.assertTrue(all(row['id'] is None for row in fixture.rows))

    def test_missing_git_cannot_skip_fresh_evidence_or_run_live_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            path.write_text('{"stale_success":true}')
            with patch.object(attack_suite.lifecycle,'settings',return_value={}), \
                    patch.object(attack_suite.subprocess,'run',side_effect=FileNotFoundError('synthetic')), \
                    patch.object(attack_suite.lifecycle,'kubeconfig') as kubeconfig, \
                    patch.object(attack_suite,'publish',return_value=False), patch('sys.stdout',new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as stopped: attack_suite.main(['--out',str(path)])
                self.assertEqual(stopped.exception.code,1)
            kubeconfig.assert_not_called()
            data=json.loads(path.read_text())
            self.assertIsNone(data['runner_commit'])
            self.assertNotIn('stale_success',data)
            self.assertEqual(data['results'][0]['verdict'],'NOT_EXERCISED')

    def test_declared_case_inventory_contains_current_mediators_and_separate_cleanup_controls(self):
        cases=attack_suite.build_cases({})
        self.assertEqual(len({c.name for c in cases}),len(cases))
        for name in ('financial_active_capability_boundary','financial_broker_database_roles','gateway_redaction_failure_rejected',
                     'ops_stale_approval_refused','financial_fixture_cleanup','financial_transport_cleanup'):
            self.assertIn(name,{c.name for c in cases})
        self.assertTrue(all(c.kind=='control' and c.always for c in cases if c.name.endswith('_cleanup')))


if __name__=='__main__': unittest.main()
