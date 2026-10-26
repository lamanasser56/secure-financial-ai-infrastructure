"""K02: the current ops observer's projected token cannot mutate or read secrets."""
import re

from live_probe_kube import one_pod, python_probe


K02 = r'''
import json, ssl, urllib.error, urllib.request
from pathlib import Path
root = Path('/var/run/secrets/kubernetes.io/serviceaccount')
token = (root / 'token').read_text().strip()
context = ssl.create_default_context(cafile=str(root / 'ca.crt'))
base = 'https://kubernetes.default.svc'
def status(method, path, data=None, content_type=None, extra=None):
    headers = {'Authorization':'Bearer ' + token}
    if content_type:
        headers['Content-Type'] = content_type
    headers.update(extra or {})
    request = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(),
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, context=context, timeout=8) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
patch = status('PATCH', '/apis/apps/v1/namespaces/apps/deployments/fault-demo?dryRun=All',
               {'metadata':{'annotations':{'assessment.probe':'dry-run'}}},
               'application/merge-patch+json')
secret = status('GET', '/api/v1/namespaces/apps/secrets/app')
execute = status('POST', '/api/v1/namespaces/apps/pods/__APP_POD__/exec?command=true&stdout=true')
create = status('POST', '/api/v1/namespaces/apps/pods?dryRun=All',
                {'apiVersion':'v1','kind':'Pod','metadata':{'name':'assessment-forbidden'},
                 'spec':{'containers':[{'name':'probe','image':'invalid.example/forbidden'}]}},
                'application/json')
impersonate = status('GET', '/api/v1/namespaces/apps/pods',
                     extra={'Impersonate-User':'system:serviceaccount:ops:ops-executor'})
print(json.dumps({'projected_token_present': bool(token), 'patch_denied':patch == 403,
                  'secret_read_denied':secret == 403, 'pod_exec_denied':execute == 403,
                  'pod_create_denied':create == 403, 'impersonation_denied':impersonate == 403}))
'''


def probe_k02(kubeconfig, *, executable='kubectl', pod=one_pod, execute=python_probe):
    observer = pod(kubeconfig, 'ops', 'app.kubernetes.io/name=ops-agent', executable=executable)
    target = pod(kubeconfig, 'apps', 'app.kubernetes.io/name=app', executable=executable)
    if not re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', target):
        raise RuntimeError('assessment:invalid_pod_name')
    return execute(kubeconfig, 'ops', observer, K02.replace('__APP_POD__', target),
                   executable=executable)


K03 = r'''
import hashlib, json, ssl, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
root = Path('/var/run/secrets/kubernetes.io/serviceaccount')
token = (root / 'token').read_text().strip()
context = ssl.create_default_context(cafile=str(root / 'ca.crt'))
base = 'https://kubernetes.default.svc'
path = '/apis/apps/v1/namespaces/apps/deployments/fault-demo'
def call(method, path, data=None, content_type=None):
    headers = {'Authorization':'Bearer ' + token}
    if content_type:
        headers['Content-Type'] = content_type
    request = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(),
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, context=context, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':')).encode()).hexdigest()
before_status, before = call('GET', path)
if before_status != 200:
    raise RuntimeError('cannot read registered target')
containers = before['spec']['template']['spec']['containers']
annotation = datetime.now(timezone.utc).isoformat()
allowed, _ = call('PATCH', path + '?dryRun=All',
    {'spec':{'template':{'metadata':{'annotations':{'kubectl.kubernetes.io/restartedAt':annotation}}}}},
    'application/strategic-merge-patch+json')
image, _ = call('PATCH', path + '?dryRun=All',
    {'spec':{'template':{'spec':{'containers':[{'name':containers[0]['name'],
                                                'image':'invalid.example/forbidden:latest'}]}}}},
    'application/strategic-merge-patch+json')
scale, _ = call('PATCH', path + '?dryRun=All', {'spec':{'replicas':999}},
    'application/strategic-merge-patch+json')
after_status, after = call('GET', path)
print(json.dumps({'projected_token_present':bool(token), 'allowed_restart_dry_run':allowed == 200,
                  'template_image_change_denied':image == 403,
                  'out_of_range_scale_denied':scale == 403,
                  'deployment_spec_unchanged':after_status == 200 and digest(before['spec']) == digest(after['spec'])}))
'''


def probe_k03(kubeconfig, *, executable='kubectl', pod=one_pod, execute=python_probe):
    executor = pod(kubeconfig, 'ops', 'app.kubernetes.io/name=ops-executor', executable=executable)
    return execute(kubeconfig, 'ops', executor, K03, executable=executable)
