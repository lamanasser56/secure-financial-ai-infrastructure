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

    def container(self, **change):
        current = json.loads(self.kubectl('-n', 'apps', 'get', 'deployment', 'fault-demo', '-o', 'json').stdout)
        container = current['spec']['template']['spec']['containers'][0]
        container.update(change)
        return {'spec': {'template': {'spec': {'containers': [container]}}}}

    def test_admission_policy_denies_any_pod_spec_change(self):
        """No rollback: a compromised ops-agent identity cannot change what a registered workload runs."""
        template = 'the Pod template may only be unchanged or changed by the rollout-restart annotation'
        leak = ['/usr/local/bin/python3.12', '-c', 'print(open("/var/run/secrets/tokens/token").read())']
        for name, patch in (
                ('command', self.container(command=leak)),
                ('args', self.container(args=['--print-key'])),
                ('env', self.container(env=[{'name': 'PYTHONPATH', 'value': '/app/platform/src:/app'}, {'name': 'FAULT_MODE', 'value': 'oom'}])),
                ('envFrom', self.container(envFrom=[{'secretRef': {'name': 'app'}}])),
                ('resources', self.container(resources={'requests': {'cpu': '20m', 'memory': '32Mi'}, 'limits': {'cpu': '2', 'memory': '1Gi'}})),
                ('workingDir', self.container(workingDir='/tmp')),
                ('readinessProbe', self.container(readinessProbe={'tcpSocket': {'port': 8081}})),
                ('lifecycle', self.container(lifecycle={'postStart': {'exec': {'command': ['/bin/true']}}})),
                ('registered image', self.container(image=GOOD.replace('a' * 64, 'b' * 64))),
                ('other workload image', self.container(image=GATEWAY)),
                ('unsigned image', self.container(image=OTHER)),
                ('securityContext', self.container(securityContext={'allowPrivilegeEscalation': True})),
                ('template labels', {'spec': {'template': {'metadata': {'labels': {'app.kubernetes.io/name': 'fault-demo', 'app.kubernetes.io/part-of': 'agent-platform', 'egress': 'gateway'}}}}}),
                ('serviceAccountName', {'spec': {'template': {'spec': {'serviceAccountName': 'app'}}}}),
                ('restart plus env', dict(self.container(env=[{'name': 'FAULT_MODE', 'value': 'none'}]),
                                          spec=dict(self.container(env=[{'name': 'FAULT_MODE', 'value': 'none'}])['spec'],
                                                    template=dict(self.container(env=[{'name': 'FAULT_MODE', 'value': 'none'}])['spec']['template'],
                                                                  metadata={'annotations': {'kubectl.kubernetes.io/restartedAt': '2026-10-11T00:00:00Z'}}))))):
            with self.subTest(name):
                self.assertDenied(self.ops_patch('apps', 'fault-demo', patch), template)

    def test_admission_policy_denies_out_of_bounds_changes(self):
        self.assertDenied(self.ops_patch('apps', 'fault-demo', {'spec': {'replicas': 4}}), 'replicas outside the registered bounds')
        self.assertDenied(self.ops_patch('platform', 'gateway', {'spec': {'replicas': 2}}), 'replicas outside the registered bounds')
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

    def test_onboarded_agent_namespace_inherits_the_controls(self):
        """agent-hello (generated by `make onboard`): restricted pods, no exposure, out of the ops agent's reach."""
        labels = json.loads(self.kubectl('get', 'namespace', 'agent-hello', '-o', 'json').stdout)['metadata']['labels']
        self.assertEqual(labels['pod-security.kubernetes.io/enforce'], 'restricted')
        pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'root', 'namespace': 'agent-hello'},
               'spec': {'serviceAccountName': 'agent', 'automountServiceAccountToken': False,
                        'containers': [{'name': 'x', 'image': GOOD, 'securityContext': {'runAsUser': 0, 'allowPrivilegeEscalation': True}}]}}
        result = self.kubectl('apply', '-f', '-', input=json.dumps(pod), check=False)
        self.assertIn('violates PodSecurity "restricted', result.stderr)
        hard = json.loads(self.kubectl('-n', 'agent-hello', 'get', 'resourcequota', 'bounds', '-o', 'json').stdout)['spec']['hard']
        self.assertEqual((hard['services.loadbalancers'], hard['services.nodeports']), ('0', '0'))
        restart = {'spec': {'template': {'metadata': {'annotations': {'kubectl.kubernetes.io/restartedAt': '2026-10-12T00:00:00Z'}}}}}
        self.assertDenied(self.ops_patch('agent-hello', 'agent', restart), 'forbidden')  # watched read-only, never changed
        for ns in ('agent-hello', 'agent-financial'):  # the ops agent can watch onboarded agents' health
            self.assertAllowed(self.kubectl('-n', ns, 'get', 'pods', as_ops=True, check=False))
            self.assertAllowed(self.kubectl('-n', ns, 'get', 'deployment', 'agent', as_ops=True, check=False))
            for args in (('get', 'secrets'), ('delete', 'pod', 'agent-x'), ('scale', 'deployment', 'agent', '--replicas', '0'),
                         ('get', 'deployment', 'other')):
                result = self.kubectl('-n', ns, *args, as_ops=True, check=False)
                with self.subTest(ns=ns, args=args):
                    self.assertIn('forbidden', result.stderr.lower())
        as_agent = ['--as', 'system:serviceaccount:agent-hello:agent', '--as-group', 'system:serviceaccounts']
        for args in (('-n', 'agent-hello', 'get', 'pods'), ('-n', 'platform', 'get', 'secrets'), ('-n', 'agent-hello', 'get', 'secret', 'agent')):
            result = self.kubectl(*args, *as_agent, check=False)
            with self.subTest(args):
                self.assertIn('forbidden', result.stderr.lower())

    def test_no_external_exposure_quota_is_declared(self):
        # Quota enforcement needs the quota controller (not in envtest); the live attack suite proves rejection.
        for ns in ('platform', 'apps', 'ops', 'agent-hello'):
            hard = json.loads(self.kubectl('-n', ns, 'get', 'resourcequota', 'bounds', '-o', 'json').stdout)['spec']['hard']
            self.assertEqual((hard['services.loadbalancers'], hard['services.nodeports']), ('0', '0'))

if __name__ == '__main__':
    unittest.main()
