"""Policies against a real Kubernetes API server (envtest: kube-apiserver + etcd, local only, no cloud).

Applies the cloud-agnostic base, then acts as the ops agent (impersonation) to prove what RBAC and the built-in
ValidatingAdmissionPolicy allow and deny, and that Pod Security "restricted" rejects a privileged Pod.
Needs ENVTEST_BIN=<dir with kube-apiserver, etcd, kubectl> (`make test-policies` downloads the pinned release).
NetworkPolicy enforcement needs a CNI and is proven on the live cluster by the attack suite instead.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import yaml

REPO = Path(__file__).resolve().parents[3]
BIN = Path(os.environ.get('ENVTEST_BIN', '/nonexistent'))
OPS = 'system:serviceaccount:ops:ops-agent'
GOOD = 'registry.example/app@sha256:' + 'a' * 64
GATEWAY = 'registry.example/gateway@sha256:' + 'c' * 64
OTHER = 'registry.example/unsigned@sha256:' + 'f' * 64


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@unittest.skipUnless((BIN / 'kube-apiserver').exists(), 'set ENVTEST_BIN (make test-policies)')
class LivePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        etcd_client, etcd_peer, api = free_port(), free_port(), free_port()
        token = secrets.token_hex(16)
        (cls.tmp / 'tokens.csv').write_text(f'{token},admin,admin,system:masters\n')
        subprocess.run(['openssl', 'genrsa', '-out', str(cls.tmp / 'sa.key'), '2048'], check=True, capture_output=True)
        cls.procs = [subprocess.Popen([str(BIN / 'etcd'), '--data-dir', str(cls.tmp / 'etcd'),
                                       '--listen-client-urls', f'http://127.0.0.1:{etcd_client}', '--advertise-client-urls', f'http://127.0.0.1:{etcd_client}',
                                       '--listen-peer-urls', f'http://127.0.0.1:{etcd_peer}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
        cls.procs.append(subprocess.Popen([str(BIN / 'kube-apiserver'), f'--etcd-servers=http://127.0.0.1:{etcd_client}',
            f'--secure-port={api}', '--bind-address=127.0.0.1', f'--cert-dir={cls.tmp / "certs"}', '--authorization-mode=RBAC',
            f'--token-auth-file={cls.tmp / "tokens.csv"}', '--service-cluster-ip-range=10.0.0.0/24', '--allow-privileged=false',
            f'--service-account-issuer=https://kubernetes.default.svc', f'--service-account-key-file={cls.tmp / "sa.key"}',
            f'--service-account-signing-key-file={cls.tmp / "sa.key"}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        cls.kubeconfig = cls.tmp / 'kubeconfig'
        cls.kubeconfig.write_text(yaml.safe_dump({'apiVersion': 'v1', 'kind': 'Config', 'current-context': 'e',
            'clusters': [{'name': 'e', 'cluster': {'server': f'https://127.0.0.1:{api}', 'insecure-skip-tls-verify': True}}],
            'users': [{'name': 'admin', 'user': {'token': token}}],
            'contexts': [{'name': 'e', 'context': {'cluster': 'e', 'user': 'admin'}}]}))
        deadline = time.time() + 60
        while cls.kubectl('get', '--raw', '/readyz', check=False).returncode != 0:
            if time.time() > deadline:
                raise RuntimeError('apiserver not ready')
            time.sleep(1)
        manifest = subprocess.run([str(BIN / 'kubectl'), 'kustomize', '--load-restrictor', 'LoadRestrictionsNone',
                                   str(REPO / 'platform/core/kubernetes')], capture_output=True, text=True, check=True).stdout
        for name, ref in (('gateway', GATEWAY), ('app', GOOD), ('ops-agent', 'registry.example/ops@sha256:' + 'd' * 64),
                          ('redactor', 'registry.example/redactor@sha256:' + 'e' * 64), ('database', 'registry.example/db@sha256:' + 'b' * 64)):
            manifest = manifest.replace('image: agent-platform/' + name + '\n', 'image: ' + ref + '\n').replace('IMAGE:' + name, ref)
        docs = [d for d in yaml.safe_load_all(manifest) if d]
        ordered = sorted(docs, key=lambda d: (d['kind'] != 'Namespace', d['kind'] == 'ValidatingAdmissionPolicyBinding'))
        cls.kubectl('apply', '-f', '-', input=yaml.safe_dump_all(ordered))
        time.sleep(3)  # policy and binding caches

    @classmethod
    def tearDownClass(cls):
        for proc in reversed(cls.procs):
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def kubectl(cls, *args, input=None, check=True, as_ops=False):
        command = [str(BIN / 'kubectl'), '--kubeconfig', str(cls.kubeconfig)]
        if as_ops:
            command += ['--as', OPS, '--as-group', 'system:serviceaccounts', '--as-group', 'system:serviceaccounts:ops']
        result = subprocess.run(command + list(args), input=input, capture_output=True, text=True)
        if check and result.returncode != 0:
            raise AssertionError(' '.join(args) + ': ' + result.stderr)
        return result

    def ops_patch(self, namespace, name, patch):
        return self.kubectl('-n', namespace, 'patch', 'deployment', name, '--type', 'merge', '-p', json.dumps(patch), as_ops=True, check=False)

    def assertAllowed(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertDenied(self, result, text):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(text, result.stderr)

    def test_ops_agent_allowed_remediations(self):
        restart = {'spec': {'template': {'metadata': {'annotations': {'kubectl.kubernetes.io/restartedAt': '2026-10-10T00:00:00Z'}}}}}
        self.assertAllowed(self.ops_patch('apps', 'fault-demo', restart))
        self.assertAllowed(self.ops_patch('platform', 'gateway', restart))
        self.assertAllowed(self.ops_patch('apps', 'fault-demo', {'spec': {'replicas': 3}}))
        self.assertAllowed(self.ops_patch('apps', 'fault-demo', {'spec': {'replicas': 1}}))
        rollback = {'spec': {'template': {'spec': {'containers': [{'name': 'workload', 'image': GOOD, 'command': ['/usr/local/bin/python3.12', '-m', 'agent_platform.programs.fault_demo'],
            'env': [{'name': 'PYTHONPATH', 'value': '/app/platform/src:/app'}, {'name': 'FAULT_MODE', 'value': 'none'}],
            'ports': [{'name': 'http', 'containerPort': 8081}], 'resources': {'requests': {'cpu': '20m', 'memory': '32Mi'}, 'limits': {'cpu': '200m', 'memory': '48Mi'}},
            'readinessProbe': {'httpGet': {'path': '/healthz', 'port': 8081}, 'periodSeconds': 5},
            'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}, 'seccompProfile': {'type': 'RuntimeDefault'}}}]}}}}
        self.assertAllowed(self.ops_patch('apps', 'fault-demo', rollback))  # bounded rollback: env/resources change, same security fields, registered image

    def test_admission_policy_denies_out_of_bounds_changes(self):
        self.assertDenied(self.ops_patch('apps', 'fault-demo', {'spec': {'replicas': 4}}), 'replicas outside the registered bounds')
        self.assertDenied(self.ops_patch('platform', 'gateway', {'spec': {'replicas': 2}}), 'replicas outside the registered bounds')
        swap = {'spec': {'template': {'spec': {'containers': [{'name': 'workload', 'image': OTHER}]}}}}
        self.assertDenied(self.ops_patch('apps', 'fault-demo', swap), 'bounded rollback to registered images')
        escalate = {'spec': {'template': {'spec': {'containers': [{'name': 'workload', 'image': GOOD, 'securityContext': {'allowPrivilegeEscalation': True}}]}}}}
        self.assertDenied(self.ops_patch('apps', 'fault-demo', escalate), 'bounded rollback to registered images')
        sa = {'spec': {'template': {'spec': {'serviceAccountName': 'app'}}}}
        self.assertDenied(self.ops_patch('apps', 'fault-demo', sa), 'bounded rollback to registered images')
        self.assertDenied(self.ops_patch('apps', 'fault-demo', {'metadata': {'labels': {'owned-by': 'agent'}}}), 'may not change selector, strategy, labels')
        self.assertDenied(self.ops_patch('apps', 'fault-demo', {'spec': {'paused': True}}), 'may not change selector, strategy, labels')

    def test_rbac_denies_everything_else(self):
        for args in (('-n', 'apps', 'get', 'secrets'), ('-n', 'platform', 'get', 'secret', 'gateway'),
                     ('-n', 'apps', 'delete', 'deployment', 'fault-demo'), ('-n', 'platform', 'patch', 'statefulset', 'postgres', '-p', '{"spec":{"replicas":0}}'),
                     ('-n', 'apps', 'create', 'deployment', 'rogue', '--image', GOOD), ('-n', 'apps', 'scale', 'deployment', 'fault-demo', '--replicas', '2'),
                     ('-n', 'ops', 'patch', 'deployment', 'ops-agent', '-p', '{"spec":{"replicas":0}}'),
                     ('-n', 'apps', 'create', 'rolebinding', 'x', '--role', 'ops-agent-remediate', '--user', 'x'),
                     ('get', 'namespaces'), ('-n', 'kube-system', 'get', 'pods')):
            result = self.kubectl(*args, as_ops=True, check=False)
            with self.subTest(args):
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('forbidden', result.stderr.lower())
        self.kubectl('-n', 'apps', 'create', 'deployment', 'rogue', '--image', GOOD)  # owner may; agent may not touch it
        self.assertDenied(self.ops_patch('apps', 'rogue', {'spec': {'replicas': 0}}), 'forbidden')

    def test_owner_is_not_restricted_by_the_agent_policy(self):
        self.assertAllowed(self.kubectl('-n', 'apps', 'patch', 'deployment', 'fault-demo', '--type', 'merge', '-p', '{"spec":{"replicas":5}}', check=False))
        self.kubectl('-n', 'apps', 'patch', 'deployment', 'fault-demo', '--type', 'merge', '-p', '{"spec":{"replicas":1}}')

    def test_pod_security_restricted_rejects_root_escalating_pods(self):
        pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'privileged', 'namespace': 'apps'},
               'spec': {'serviceAccountName': 'fault-demo', 'automountServiceAccountToken': False,
                        'containers': [{'name': 'x', 'image': GOOD, 'securityContext': {'runAsUser': 0, 'allowPrivilegeEscalation': True}}]}}
        result = self.kubectl('apply', '-f', '-', input=json.dumps(pod), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('violates PodSecurity "restricted', result.stderr)

    def test_no_external_exposure_quota_is_declared(self):
        # Quota enforcement needs the quota controller (not in envtest); the live attack suite proves rejection.
        for ns in ('platform', 'apps', 'ops'):
            hard = json.loads(self.kubectl('-n', ns, 'get', 'resourcequota', 'bounds', '-o', 'json').stdout)['spec']['hard']
            self.assertEqual((hard['services.loadbalancers'], hard['services.nodeports']), ('0', '0'))

if __name__ == '__main__':
    unittest.main()
