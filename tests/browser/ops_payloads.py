"""Offline browser fixtures projected through current Console, Ops and posture code."""
import contextlib
import io
import json
from pathlib import Path
import sys
import time

root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(root), str(root/'platform/core/src'), str(root/'platform/core/tests'), str(root/'platform/agents/financial')]
from agent_platform.app import ClusterOperations
from agent_platform.ops import approval, registry
from agent_platform.ops.agent import Agent
from fixtures import FakeClient, REGISTRY, deployment, pod
from test_console import KubeStub, make, finding, ops_answers

clock = time.time()
answers = ops_answers()
for f in answers['/v1/snapshot']['findings'].values():
    f['facts']['observed_at'] = clock - 5
for event in answers['/v1/activity']['events']: event['at'] = clock - 10
console = make(answers)
console._clock = lambda: clock
config = next(d['data'] for d in console.facts['documents'] if d['kind']=='ConfigMap' and d['metadata']['name']=='ops-agent-registry')
observed = next(d['data'] for d in console.facts['documents'] if d['kind']=='ConfigMap' and d['metadata']['name']=='ops-agent-observe')
targets = {**registry.parse(config), **registry.parse_observe(observed)}
security = Agent(KubeStub(), targets, None, clock=lambda: clock).posture()
answers['/v1/posture'] = security
with contextlib.redirect_stdout(io.StringIO()):
    agent = Agent(FakeClient(deployment(available=0), [pod(ready=False)]), {'apps.fault-demo': REGISTRY['apps.fault-demo']}, None, clock=lambda: clock)
    agent.scan()
snapshot = agent.snapshot()
proposal = next(p for p in snapshot['pending'] if p['action']=='restart')
snapshot['pending'] = [proposal]
for key, target in targets.items():
    if key in snapshot['findings']: continue
    value = answers['/v1/snapshot']['findings'].get(key) or finding(target.namespace, target.name)
    value['facts']['observed_at'] = clock - 5
    value['observe_only'] = target.observe_only
    snapshot['findings'][key] = value
snapshot['denials'] = []
private, _ = approval.generate_keypair()
projection = ClusterOperations({'approver_private_key':private}, clock=lambda:clock)
projection._call = lambda method, path, body=None: snapshot if path=='/v1/snapshot' else security
agents = console.agents()
endpoints = {'/api/console/agents': agents, '/api/console/topology': console.topology(), '/api/console/activity?limit=3': console.activity(3)}
for a in agents['agents']: endpoints['/api/console/onboarding/'+a['name']] = console.onboarding(a['name'])
print(json.dumps({'endpoints':endpoints, 'overview':projection.handle({'operation':'overview'}), 'security':security, 'proposal':proposal, 'now':clock}))
