"""O03: exact-object approval races against the disposable fault-demo Deployment.

The probe signs inside the app Pod and executes inside the Ops Pod. A one-use
approval never leaves the disposable cluster. Only the zero-replica fault-demo
Deployment may be replaced; the original cluster is rejected by run binding.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

from live_case_guard import PROJECT_PATTERN
from live_probe_kube import one_pod


SNAPSHOT = r'''
import json, urllib.request
from pathlib import Path
c = json.loads(Path('/secrets/ops/ops.json').read_text())
request = urllib.request.Request('http://127.0.0.1:8090/v1/snapshot',
    headers={'Authorization':'Bearer ' + c['api_key']})
with urllib.request.urlopen(request, timeout=8) as response:
    finding = json.load(response)['findings']['apps.fault-demo']
print(json.dumps({key:finding[key] for key in ('uid','resource_version','evidence_digest','finding')}))
'''

SIGN = r'''
import json
from pathlib import Path
from agent_platform.ops.approval import Signer
c = json.loads(Path('/secrets/app/app.json').read_text())
proposal = json.loads(__PROPOSAL__)
print(Signer(c['approver_private_key']).sign(proposal))
'''

EXECUTE = r'''
import json, urllib.request
from pathlib import Path
c = json.loads(Path('/secrets/ops/ops.json').read_text())
body = {'proposal':json.loads(__PROPOSAL__), 'approval':__TOKEN__}
request = urllib.request.Request('http://ops-executor.ops.svc.cluster.local:8091/execute',
    data=json.dumps(body).encode(), method='POST',
    headers={'Authorization':'Bearer ' + c['executor_key'], 'Content-Type':'application/json'})
with urllib.request.urlopen(request, timeout=20) as response:
    result = json.load(response)
print(json.dumps({'target_replaced':result == {'result':'DENIED','code':'TARGET_REPLACED'},
                  'object_changed':result == {'result':'DENIED','code':'OBJECT_CHANGED'}}))
'''


def command(kubeconfig, args, *, input=None, executable='kubectl', run=subprocess.run):
    result = run([str(executable), '--kubeconfig=' + str(kubeconfig), *args],
                 input=input, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError('assessment:o03_kubectl_failed')
    return result.stdout


def remote(kubeconfig, namespace, pod, script, *, executable='kubectl', call=command):
    return call(kubeconfig, ['-n', namespace, 'exec', '-i', pod, '--',
                             '/usr/local/bin/python3.12', '-'],
                input=script, executable=executable).strip()


def proposal(finding):
    if finding['finding'] != 'HEALTHY' or not all(finding.get(k) for k in
            ('uid', 'resource_version', 'evidence_digest')):
        raise RuntimeError('assessment:o03_target_not_healthy')
    return {'request_id': str(uuid.uuid4()), 'target': 'apps.fault-demo',
            'action': 'restart', 'arguments': {},
            'args_digest': hashlib.sha256(b'{}').hexdigest(),
            'evidence_digest': finding['evidence_digest'],
            'uid': finding['uid'], 'resource_version': finding['resource_version'],
            'finding': finding['finding'], 'created_at': 0, 'expires_at': 0,
            'state': 'proposed'}


def bound_run(manifest, run_dir, kubeconfig):
    run_dir = Path(run_dir).resolve()
    if (not PROJECT_PATTERN.fullmatch(manifest['disposable_project_id'])
            or Path(kubeconfig).resolve() != run_dir / 'kube' / 'kubeconfig'
            or json.loads((run_dir / 'initial-manifest.json').read_text()) != manifest
            or not (run_dir / 'evidence' / 'bundle-applied.json').is_file()):
        raise RuntimeError('assessment:o03_disposable_run_binding_required')


def probe_o03(kubeconfig, run_dir, manifest, *, executable='kubectl',
              call=command, pod=one_pod, sleep=time.sleep):
    bound_run(manifest, run_dir, kubeconfig)
    base = ['-n', 'apps', 'get', 'deployment', 'fault-demo', '-o', 'json']
    original = json.loads(call(kubeconfig, base, executable=executable))
    expected_digest = manifest['image_digests']['app'].split('@', 1)[1]
    images = [c['image'] for c in original['spec']['template']['spec']['containers']]
    if (original['spec'].get('replicas') != 0 or len(images) != 1
            or not images[0].endswith('@' + expected_digest)):
        raise RuntimeError('assessment:o03_unexpected_fault_target')
    ops = pod(kubeconfig, 'ops', 'app.kubernetes.io/name=ops-agent', executable=executable)
    app = pod(kubeconfig, 'apps', 'app.kubernetes.io/name=app', executable=executable)

    def finding(uid):
        for _ in range(8):
            value = json.loads(remote(kubeconfig, 'ops', ops, SNAPSHOT,
                                      executable=executable, call=call))
            if value['uid'] == uid:
                return value
            sleep(5)
        raise RuntimeError('assessment:o03_fresh_observation_missing')

    def attempt(value):
        item = proposal(value)
        encoded = json.dumps(json.dumps(item))
        token = remote(kubeconfig, 'apps', app, SIGN.replace('__PROPOSAL__', encoded),
                       executable=executable, call=call)
        if not token or len(token) > 4096:
            raise RuntimeError('assessment:o03_approval_missing')
        result = json.loads(remote(kubeconfig, 'ops', ops,
                                   EXECUTE.replace('__PROPOSAL__', encoded)
                                   .replace('__TOKEN__', json.dumps(token)),
                                   executable=executable, call=call))
        return result

    old = finding(original['metadata']['uid'])
    replacement = {key: original[key] for key in ('apiVersion', 'kind', 'spec')}
    replacement['metadata'] = {key: original['metadata'][key] for key in
                               ('name', 'namespace', 'labels', 'annotations')
                               if key in original['metadata']}
    call(kubeconfig, ['-n', 'apps', 'replace', '--force', '-f', '-'],
         input=json.dumps(replacement), executable=executable)
    current = json.loads(call(kubeconfig, base, executable=executable))
    uid_changed = current['metadata']['uid'] != original['metadata']['uid']
    spec_preserved = current['spec'] == original['spec']
    uid_result = attempt(old) if uid_changed and spec_preserved else {}

    fresh = finding(current['metadata']['uid'])
    call(kubeconfig, ['-n', 'apps', 'annotate', 'deployment/fault-demo',
                      'assessment.o03/version=' + uuid.uuid4().hex], executable=executable)
    changed = json.loads(call(kubeconfig, base, executable=executable))
    version_changed = changed['metadata']['resourceVersion'] != fresh['resource_version']
    rv_result = attempt(fresh) if version_changed and changed['spec'] == original['spec'] else {}
    final = json.loads(call(kubeconfig, base, executable=executable))
    return {'uid_changed': uid_changed, 'uid_race_denied': uid_result.get('target_replaced') is True,
            'resource_version_changed': version_changed,
            'rv_race_denied': rv_result.get('object_changed') is True,
            'target_spec_unchanged': spec_preserved and final['spec'] == original['spec'],
            'exact_image_digest_unchanged': all(c['image'].endswith('@' + expected_digest)
                for c in final['spec']['template']['spec']['containers'])}
