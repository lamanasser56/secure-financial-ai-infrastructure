"""D02: real synthetic SDP at the current boundary; one private stub dispatch."""
import json

from live_probe_kube import kubectl, one_pod, python_probe


STATS = r'''
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8080/stats', timeout=5) as response:
    print(json.dumps(json.load(response)))
'''

WORKER = r'''
import json, socket, urllib.request
from pathlib import Path
c = json.loads(Path('/secrets/agent/agent.json').read_text())
def post(url, key, value):
    request = urllib.request.Request(url, data=json.dumps(value).encode(),
        headers={'Authorization':'Bearer '+key, 'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, json.load(response)
redactor = 'http://redactor.platform.svc.cluster.local:4003/redact'
checks = {}
for name, text, canary, category in (
        ('email', 'Email alice@example.com.', 'alice@example.com', 'EMAIL_ADDRESS'),
        ('phone', 'Call +1 202-555-0101.', '+1 202-555-0101', 'PHONE_NUMBER')):
    status, value = post(redactor, c['redactor_key'], {'text':text})
    checks[name + '_masked'] = (status == 200 and canary not in value.get('text','')
                               and category in value.get('categories', []))
try:
    conn = socket.create_connection(('provider-stub.assess-probes.svc.cluster.local', 8080), timeout=2)
    conn.close()
    direct = True
except OSError:
    direct = False
checks['provider_direct_denied'] = not direct
status, value = post('http://gateway-boundary.platform.svc.cluster.local:4000/v1/chat/completions',
    c['gateway_key'], {'model':'secure-financial-chat', 'messages':[
        {'role':'user','content':'Call +1 202-555-0101.'}], 'temperature':0,
        'max_tokens':64, 'stream':False, 'response_format':{'type':'json_object'}})
checks['gateway_private_response'] = (status == 200 and isinstance(value.get('choices'), list)
                                      and len(value['choices']) == 1)
print(json.dumps(checks))
'''


def stub_stats(kubeconfig, pod, *, executable='kubectl', run=kubectl):
    command = [str(executable), '--kubeconfig=' + str(kubeconfig), '-n', 'assess-probes',
               'exec', '-i', pod, '--', '/usr/local/bin/python3.12', '-']
    value = json.loads(run(command, input=STATS))
    if (set(value) != {'requests', 'raw_canary_seen'} or type(value['requests']) is not int
            or not 0 <= value['requests'] <= 200 or type(value['raw_canary_seen']) is not bool):
        raise RuntimeError('assessment:stub_stats_invalid')
    return value


def probe(kubeconfig, *, executable='kubectl', pod=one_pod,
          execute=python_probe, stats=stub_stats):
    stub = pod(kubeconfig, 'assess-probes', 'assessment.role=provider-stub', executable=executable)
    worker = pod(kubeconfig, 'agent-financial', 'agent-platform/user-slot=u1', executable=executable)
    before = stats(kubeconfig, stub, executable=executable)
    if before['raw_canary_seen']:
        raise RuntimeError('assessment:provider_raw_canary_seen_before_case')
    checks = execute(kubeconfig, 'agent-financial', worker, WORKER, executable=executable)
    after = stats(kubeconfig, stub, executable=executable)
    checks['one_stub_dispatch'] = after['requests'] == before['requests'] + 1
    checks['stub_raw_canary_absent'] = not after['raw_canary_seen']
    return checks
