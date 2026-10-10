#!/usr/bin/env python3
"""GKE lifecycle for the agent platform (called by the Makefile). Runs on the owner's laptop.

  plan           terraform init + plan (saved plan + JSON) of platform/clouds/gke/terraform/root   [cloud read]
  apply          apply exactly the saved, reviewed plan                                             [cloud write]
  kubeconfig     private kubeconfig for the DNS endpoint; credential = fresh gcloud token per call
  attest REF..   KMS attestation for already-signed digests (owner identity; CI attests new images)
  up             scale the pool 0->1, render + validate + apply manifests, bootstrap, wait ready     [cloud write]
  down           snapshot the Postgres disk, then scale the pool to 0                               [cloud write]
  fault F        oom | crashloop | badimage on apps/fault-demo (owner identity, not the agent)      [cloud write]
  port-forward   kubectl port-forward deploy/app 8080:8080 (the only way in)
  inventory      read-only: everything billable that exists in the project                          [cloud read]
Terraform uses the user-ADC guard (no static token, no metadata dependency). No command prints secrets.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROOT = HERE / 'terraform/root'
STATE = Path.home() / '.local/state/secure-financial-ai-infrastructure/agent-platform'
TOOLS = Path.home() / 'portfolio-sdp-us-east1-401f097/tools'
TF, KUBECTL = TOOLS / 'terraform', TOOLS / 'kubectl'
TF_SHA256 = '2807bc0c4edde23aabe665a82482398e0b67c537bcf556669a9b0e9580c4f510'
NAME, ZONE, POOL = 'agent-platform', 'us-east1-b', 'work'


def run(*command, check=True, capture=False, env=None, input=None):
    result = subprocess.run([str(c) for c in command], check=False, text=True, env=env, input=input,
                            capture_output=capture)
    if check and result.returncode != 0:
        raise SystemExit('lifecycle:command_failed:' + Path(str(command[0])).name + ' ' + str(command[1] if len(command) > 1 else ''))
    return result


def settings():
    path = STATE / 'settings.json'  # project_id, project_number, gke_version, state_bucket (private, 0600, never committed)
    return json.loads(path.read_text())


def guard_env():
    """Refreshing user ADC for Terraform (the token guard proven for the laptop control plane)."""
    import importlib.util
    os.environ['AGENT_PLATFORM_PROJECT_ID'] = settings()['project_id']
    spec = importlib.util.spec_from_file_location('token_guard', HERE / 'token_guard.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    if hashlib.sha256(TF.read_bytes()).hexdigest() != TF_SHA256:
        raise SystemExit('lifecycle:terraform_binary')
    return module.user_adc_env()


def tf(*args, env):
    return run(TF, '-chdir=' + str(ROOT), *args, env=env)


def plan():
    s, env = settings(), guard_env()
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    tfvars = STATE / 'platform.tfvars.json'
    tfvars.write_text(json.dumps({'project_id': s['project_id'], 'project_number': s['project_number'], 'gke_version': s['gke_version']}))
    os.chmod(tfvars, 0o600)
    tf('init', '-input=false', '-lockfile=readonly', '-backend-config=bucket=' + s['state_bucket'], env=env)
    out = STATE / 'platform.tfplan'
    tf('plan', '-input=false', '-var-file=' + str(tfvars), '-out=' + str(out), env=env)
    shown = run(TF, '-chdir=' + str(ROOT), 'show', '-json', str(out), capture=True, env=env).stdout
    (STATE / 'platform-plan.json').write_text(shown)
    summary = summarize(json.loads(shown))
    (STATE / 'platform-plan-summary.json').write_text(json.dumps(summary, indent=1, sort_keys=True))
    print(json.dumps({'saved_plan_sha256': hashlib.sha256(out.read_bytes()).hexdigest(), **summary['counts']}, sort_keys=True))


def summarize(plan):
    counts, changes = {'create': 0, 'update': 0, 'delete': 0, 'replace': 0, 'read': 0}, []
    for rc in plan.get('resource_changes', []):
        actions = rc['change']['actions']
        if actions == ['no-op']:
            continue
        key = 'replace' if set(actions) == {'create', 'delete'} else actions[0]
        counts[key] += 1
        changes.append({'address': rc['address'], 'actions': actions})
    return {'counts': counts, 'changes': changes, 'complete': plan.get('complete'), 'errored': plan.get('errored')}


def apply():
    env = guard_env()
    out = STATE / 'platform.tfplan'
    summary = json.loads((STATE / 'platform-plan-summary.json').read_text())
    if summary['counts']['delete'] or summary['counts']['replace']:
        raise SystemExit('lifecycle:plan_destroys_something_review_required')
    tf('apply', '-input=false', str(out), env=env)


def kubeconfig():
    s = settings()
    described = json.loads(run('gcloud', 'container', 'clusters', 'describe', NAME, '--location', ZONE, '--project', s['project_id'],
                               '--format=json', capture=True).stdout)
    endpoint = described['controlPlaneEndpointsConfig']['dnsEndpointConfig']['endpoint']
    helper = STATE / 'gcloud-token-exec.sh'
    helper.write_text('#!/bin/sh\nt=$(gcloud auth print-access-token) || exit 1\n'
                      'printf \'{"apiVersion":"client.authentication.k8s.io/v1beta1","kind":"ExecCredential","status":{"token":"%s"}}\' "$t"\n')
    os.chmod(helper, 0o700)
    config = {'apiVersion': 'v1', 'kind': 'Config', 'current-context': NAME,
              'clusters': [{'name': NAME, 'cluster': {'server': 'https://' + endpoint}}],
              'users': [{'name': NAME, 'user': {'exec': {'apiVersion': 'client.authentication.k8s.io/v1beta1', 'command': str(helper),
                                                         'interactiveMode': 'Never'}}}],
              'contexts': [{'name': NAME, 'context': {'cluster': NAME, 'user': NAME}}]}
    path = STATE / 'kubeconfig'
    path.write_text(json.dumps(config)); os.chmod(path, 0o600)
    return path


def kubectl(*args, **kw):
    return run(KUBECTL, '--kubeconfig', str(STATE / 'kubeconfig'), *args, **kw)


def outputs():
    s = settings()
    return {'project_id': s['project_id'], 'control_plane_cidr': '172.16.0.16/28',
            'gateway_gsa': f'{NAME}-gateway@{s["project_id"]}.iam.gserviceaccount.com',
            'redactor_gsa': f'google-sdp-runtime@{s["project_id"]}.iam.gserviceaccount.com'}


def resize(count):
    s = settings()
    run('gcloud', 'container', 'clusters', 'resize', NAME, '--node-pool', POOL, '--num-nodes', str(count),
        '--location', ZONE, '--project', s['project_id'], '--quiet')


def up():
    started = time.time()
    resize(1)
    kubeconfig()
    o = outputs()
    rendered = run(sys.executable, '-B', HERE / 'render.py', '--project-id', o['project_id'], '--control-plane-cidr', o['control_plane_cidr'],
                   '--gateway-gsa', o['gateway_gsa'], '--redactor-gsa', o['redactor_gsa'], '--kubectl', KUBECTL, capture=True).stdout
    kubectl('apply', '--server-side', '--field-manager=agent-platform', '-f', '-', input=rendered)
    run(sys.executable, '-B', '-m', 'agent_platform.platform_secrets', '--kubectl', KUBECTL,
        env=dict(os.environ, PYTHONPATH=str(REPO / 'platform/core/src') + ':' + str(REPO), KUBECONFIG=str(STATE / 'kubeconfig')))
    kubectl('-n', 'platform', 'rollout', 'status', 'statefulset/postgres', '--timeout=300s')
    kubectl('-n', 'platform', 'wait', '--for=condition=complete', 'job/schema', '--timeout=600s')
    for ns, name in (('platform', 'gateway'), ('platform', 'redactor'), ('apps', 'app'), ('apps', 'fault-demo'), ('ops', 'ops-agent')):
        kubectl('-n', ns, 'rollout', 'status', 'deployment/' + name, '--timeout=300s')
    print(json.dumps({'result': 'UP', 'minutes': round((time.time() - started) / 60, 1), 'access': 'make port-forward -> http://127.0.0.1:8080/'}))


def down():
    s = settings()
    kubeconfig()
    pv = kubectl('-n', 'platform', 'get', 'pvc', 'data-postgres-0', '-o', 'jsonpath={.spec.volumeName}', capture=True).stdout.strip()
    disk = kubectl('get', 'pv', pv, '-o', 'jsonpath={.spec.csi.volumeHandle}', capture=True).stdout.strip().rsplit('/', 1)[-1]
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    run('gcloud', 'compute', 'disks', 'snapshot', disk, '--zone', ZONE, '--project', s['project_id'],
        '--snapshot-names', f'{NAME}-postgres-{stamp}', '--labels', 'purpose=agent-platform', '--quiet')
    resize(0)
    print(json.dumps({'result': 'DOWN', 'snapshot': f'{NAME}-postgres-{stamp}', 'nodes': 0}))


FAULTS = {'oom': {'spec': {'template': {'spec': {'containers': [{'name': 'workload', 'env': [
              {'name': 'PYTHONPATH', 'value': '/app/platform/src:/app'}, {'name': 'FAULT_MODE', 'value': 'oom'}]}]}}}},
          'crashloop': {'spec': {'template': {'spec': {'containers': [{'name': 'workload', 'env': [
              {'name': 'PYTHONPATH', 'value': '/app/platform/src:/app'}, {'name': 'FAULT_MODE', 'value': 'crashloop'}]}]}}}},
          'inject': {'spec': {'template': {'spec': {'containers': [{'name': 'workload', 'env': [
              {'name': 'PYTHONPATH', 'value': '/app/platform/src:/app'}, {'name': 'FAULT_MODE', 'value': 'inject'}]}]}}}}}


def fault(kind):
    kubeconfig()
    if kind == 'badimage':
        unsigned = 'us-east1-docker.pkg.dev/' + settings()['project_id'] + '/sdp-evaluation-images/unsigned-demo@sha256:' + '0' * 64
        kubectl('-n', 'apps', 'set', 'image', 'deployment/fault-demo', 'workload=' + unsigned)
    elif kind in FAULTS:
        kubectl('-n', 'apps', 'patch', 'deployment', 'fault-demo', '--type', 'strategic', '-p', json.dumps(FAULTS[kind]))
    else:
        raise SystemExit('usage: fault oom|crashloop|inject|badimage')
    print(json.dumps({'fault': kind, 'target': 'apps/fault-demo', 'applied_by': 'owner'}))


def attest(refs):
    s = settings()
    for ref in refs:
        if '@sha256:' not in ref:
            raise SystemExit('lifecycle:digest_required')
        run('gcloud', 'beta', 'container', 'binauthz', 'attestations', 'sign-and-create', '--project', s['project_id'],
            '--artifact-url', ref, '--attestor', f'projects/{s["project_id"]}/attestors/{NAME}-ci',
            '--keyversion', f'projects/{s["project_id"]}/locations/us-east1/keyRings/{NAME}/cryptoKeys/binauthz-attestor/cryptoKeyVersions/1')
        print(json.dumps({'attested': ref}))


def port_forward():
    kubeconfig()
    os.execv(str(KUBECTL), [str(KUBECTL), '--kubeconfig', str(STATE / 'kubeconfig'), '-n', 'apps', 'port-forward',
                            '--address', '127.0.0.1', 'deployment/app', '8080:8080'])


def inventory():
    s = settings(); p = s['project_id']
    reads = {'clusters': ['container', 'clusters', 'list'], 'instances': ['compute', 'instances', 'list'],
             'disks': ['compute', 'disks', 'list'], 'snapshots': ['compute', 'snapshots', 'list'],
             'addresses': ['compute', 'addresses', 'list'], 'forwarding_rules': ['compute', 'forwarding-rules', 'list'],
             'routers': ['compute', 'routers', 'list'], 'networks': ['compute', 'networks', 'list'],
             'kms_keys': ['kms', 'keys', 'list', '--keyring', NAME, '--location', 'us-east1'],
             'log_buckets': ['logging', 'buckets', 'list', '--location', 'us-east1'],
             'repositories': ['artifacts', 'repositories', 'list']}
    result = {}
    for key, args in reads.items():
        q = run('gcloud', *args, '--project', p, '--format=json', capture=True, check=False)
        result[key] = [x.get('name', '').rsplit('/', 1)[-1] for x in json.loads(q.stdout or '[]')] if q.returncode == 0 else 'UNREADABLE'
    print(json.dumps(result, indent=1, sort_keys=True))


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['plan', 'apply', 'kubeconfig', 'attest', 'up', 'down', 'fault', 'port-forward', 'inventory'])
    parser.add_argument('args', nargs='*')
    a = parser.parse_args(argv)
    {'plan': plan, 'apply': apply, 'kubeconfig': lambda: print(kubeconfig()), 'up': up, 'down': down,
     'port-forward': port_forward, 'inventory': inventory}.get(a.command, lambda: None)()
    if a.command == 'fault':
        fault((a.args or [''])[0])
    if a.command == 'attest':
        attest(a.args)


if __name__ == '__main__':
    main(sys.argv[1:])
