"""Owner-only transactional test instrumentation for current workers. No production transport fallback."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import time
import uuid
from attack_fixture_spec import MONTH, OWN_MARKER, FOREIGN_MARKER


class NotExercised(RuntimeError):
    pass


class RestoreFailed(RuntimeError):
    pass


def get_deployment(k, namespace, name):
    result = k('-n', namespace, 'get', 'deployment', name, '-o', 'json')
    if result.returncode:
        raise NotExercised('workload_unavailable')
    return json.loads(result.stdout)


def replace_owned(k, namespace, name, uid, path, old, new):
    result = k('-n', namespace, 'patch', 'deployment', name, '--type=json', '-p', json.dumps([
        {'op': 'test', 'path': '/metadata/uid', 'value': uid},
        {'op': 'test', 'path': path, 'value': old}, {'op': 'replace', 'path': path, 'value': new}]))
    if result.returncode:
        raise RestoreFailed('owned_field_precondition_failed')


def replace_fields(k, namespace, name, uid, fields):
    patch = [{'op':'test','path':'/metadata/uid','value':uid}]
    patch += [{'op':'test','path':path,'value':old} for path,old,_ in fields]
    patch += [{'op':'replace','path':path,'value':new} for path,_,new in fields]
    if k('-n',namespace,'patch','deployment',name,'--type=json','-p',json.dumps(patch)).returncode:
        raise RestoreFailed('owned_fields_precondition_failed')


@contextmanager
def temporary_annotation(k):
    namespace,name,key='apps','fault-demo','attack-suite/touched'
    original=get_deployment(k,namespace,name)
    metadata=original['metadata']; annotations=metadata.get('annotations') or {}
    escaped='/metadata/annotations/attack-suite~1touched'
    tag=uuid.uuid4().hex
    patch=[{'op':'test','path':'/metadata/uid','value':metadata['uid']}]
    patch.append({'op':'test','path':'/metadata/annotations','value':annotations} if 'annotations' in metadata else
                 {'op':'test','path':'/metadata/resourceVersion','value':metadata['resourceVersion']})
    patch.append({'op':'add','path':escaped,'value':tag} if 'annotations' in metadata else
                 {'op':'add','path':'/metadata/annotations','value':{key:tag}})
    if k('-n',namespace,'patch','deployment',name,'--type=json','-p',json.dumps(patch)).returncode:
        raise RestoreFailed('annotation_precondition_failed')
    try:
        yield
    finally:
        patch=[{'op':'test','path':'/metadata/uid','value':metadata['uid']},
               {'op':'test','path':escaped,'value':tag},
               {'op':'replace','path':escaped,'value':annotations[key]} if key in annotations else {'op':'remove','path':escaped}]
        if k('-n',namespace,'patch','deployment',name,'--type=json','-p',json.dumps(patch)).returncode:
            raise RestoreFailed('annotation_restore_failed')


@contextmanager
def temporary_fault(k, mode):
    from agent_platform.ops.actions import RESTART_ANNOTATION
    namespace,name='apps','fault-demo'
    original=get_deployment(k,namespace,name)
    if original['spec'].get('replicas',1) != 0 or mode not in ('wedge','inject'):
        raise NotExercised('fault_target_requires_declared_stopped_state')
    template=deepcopy(original['spec']['template']); changed=deepcopy(template)
    if mode == 'inject':
        container=changed['spec']['containers'][0]
        container['env']=[e for e in container.get('env',[]) if e['name'] != 'FAULT_MODE']+[{'name':'FAULT_MODE','value':'inject'}]
    uid=original['metadata']['uid']
    replace_fields(k,namespace,name,uid,[('/spec/template',template,changed),('/spec/replicas',0,1)])
    try:
        if mode == 'wedge':
            if k('-n',namespace,'rollout','status','deployment/'+name,'--timeout=180s').returncode:
                raise NotExercised('fault_positive_control_unavailable')
            code="import urllib.request as u; u.build_opener(u.ProxyHandler({})).open(u.Request('http://127.0.0.1:8081/wedge',method='POST'),timeout=5)"
            if k('-n',namespace,'exec','deployment/'+name,'--','/usr/local/bin/python3.12','-c',code).returncode:
                raise NotExercised('runtime_fault_unavailable')
        yield
    finally:
        current=get_deployment(k,namespace,name)
        def stable(value):
            value=deepcopy(value)
            metadata=value.setdefault('metadata',{})
            annotations=metadata.get('annotations') or {}
            annotations.pop(RESTART_ANNOTATION,None)
            if not annotations: metadata.pop('annotations',None)
            return value
        actual=current['spec']['template']
        if stable(actual) != stable(changed) or current['spec'].get('replicas',1) != 1:
            raise RestoreFailed('fault_template_changed_by_other_owner')
        replace_fields(k,namespace,name,uid,[('/spec/template',actual,template),('/spec/replicas',1,0)])
        if k('-n',namespace,'rollout','status','deployment/'+name,'--timeout=180s').returncode:
            raise RestoreFailed('fault_restore_incomplete')


@contextmanager
def temporary_scale(k, namespace, name, replicas):
    original = get_deployment(k, namespace, name)
    desired = original['spec'].get('replicas', 1)
    if desired < 1:
        raise NotExercised('positive_replicas_required')
    uid = original['metadata']['uid']
    replace_owned(k, namespace, name, uid, '/spec/replicas', desired, replicas)
    try:
        yield
    finally:
        replace_owned(k, namespace, name, uid, '/spec/replicas', replicas, desired)
        if k('-n', namespace, 'rollout', 'status', 'deployment/' + name, '--timeout=180s').returncode:
            raise RestoreFailed('restored_workload_not_ready')


@contextmanager
def temporary_worker(k, namespace, name, source):
    original = get_deployment(k, namespace, name)
    template = deepcopy(original['spec']['template'])
    if len(template['spec']['containers']) != 1:
        raise NotExercised('probe_requires_single_worker_container')
    changed = deepcopy(template)
    changed['spec']['containers'][0]['command'] = ['/usr/local/bin/python3.12', '-c', source]
    changed['spec']['containers'][0].pop('args', None)
    def patch(old, new):
        replace_owned(k, namespace, name, original['metadata']['uid'], '/spec/template', old, new)
    patch(template, changed)
    try:
        rolled = k('-n', namespace, 'rollout', 'status', 'deployment/' + name, '--timeout=180s')
        if rolled.returncode:
            raise NotExercised('probe_rollout_failed')
        yield
    finally:
        # Test-and-replace the exact owned template. Never clobber a concurrent operator edit.
        patch(changed, template)
        if k('-n', namespace, 'rollout', 'status', 'deployment/' + name, '--timeout=180s').returncode:
            raise RestoreFailed('restored_worker_not_ready')


CONTROL = """import json,sys,urllib.request,urllib.error
c=json.load(open('/secrets/agent/agent.json'))
b=sys.stdin.read().encode()
r=urllib.request.Request('http://127.0.0.1:8081/probe',data=b,method='POST',headers={'Authorization':'Bearer '+c['worker_key'],'Content-Type':'application/json'})
try:
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(r,timeout=15) as response: print(response.read().decode())
except urllib.error.HTTPError:
 raise SystemExit(1)
"""


def control(k, namespace, worker, body):
    result = k('-n', namespace, 'exec', '-i', 'deployment/' + worker, '--', '/usr/local/bin/python3.12', '-c', CONTROL,
               input=json.dumps(body))
    if result.returncode:
        raise NotExercised('probe_control_unavailable')
    return json.loads(result.stdout)


def active_pair(ask, inspect, finish, *, timeout=20):
    """Both real turns stay open until all cross-worker attempts and their positive controls finish."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        turns = [pool.submit(ask, i) for i in range(2)]
        try:
            tokens, deadline = [None, None], time.monotonic() + timeout
            while not all(tokens):
                if time.monotonic() >= deadline or any(t.done() for t in turns):
                    raise NotExercised('active_turn_not_established')
                for i in range(2):
                    if not tokens[i]:
                        tokens[i] = inspect(i, {'operation': 'active'}).get('capability')
                if not all(tokens):
                    time.sleep(0.2)
            summaries = []
            markers = (OWN_MARKER, FOREIGN_MARKER)
            for i in range(2):
                summaries.append(inspect(i, {'operation': 'exercise', 'foreign': tokens[1-i],
                    'own_marker': markers[i], 'foreign_marker': markers[1-i], 'month':MONTH}))
        finally:
            failures = []
            for i in range(2):
                try:
                    finish(i, {'operation': 'finish'})
                except Exception:
                    failures.append(i)
            if failures:
                raise RestoreFailed('active_probe_turn_not_released')
        try:
            responses = [turn.result(timeout=10) for turn in turns]
        except Exception:
            raise NotExercised('frontdoor_turn_unavailable') from None
        if any(response.get('status') != 'probe_complete' for response in responses):
            raise NotExercised('active_turn_did_not_finish')
        return all(s.get('verdict') == 'PASS' for s in summaries), {'workers': summaries}


PAIR_ATTEMPTS = 2  # establishing two simultaneous turns is timing-sensitive; the boundary checks themselves are never retried


def run_capability_probe(k, app, sessions, workers, *, attempts=PAIR_ATTEMPTS, pair=None, sleep=time.sleep):
    from contextlib import ExitStack
    source = (Path(__file__).parent / 'attack_probes/financial_probe.py').read_text()
    pair = pair or active_pair
    with ExitStack() as stack:
        for worker in workers:
            stack.enter_context(temporary_worker(k, 'agent-financial', worker, source))
        first = None
        for attempt in range(1, attempts + 1):
            try:
                ok, evidence = pair(lambda i: app.ask(sessions[i], 'Synthetic active broker boundary probe.'),
                    lambda i, body: control(k, 'agent-financial', workers[i], body),
                    lambda i, body: control(k, 'agent-financial', workers[i], body))
            except NotExercised as error:
                first = first or str(error)
                if attempt == attempts:
                    raise
                sleep(5)
                continue
            evidence = dict(evidence, pair_attempts=attempt)
            if first:
                evidence['first_attempt_reason'] = first
            return ok, evidence
