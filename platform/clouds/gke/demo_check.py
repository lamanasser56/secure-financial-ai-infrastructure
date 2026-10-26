#!/usr/bin/env python3
"""Read-only release readiness. Every missing prerequisite fails; output contains closed facts only.

Uses the same selected render as make up. Required Secret names come from its references, and every
required workload and running container must match it. Image verification checks cryptography,
the CI identity/workflow revision and declared KMS authority, rather than registry metadata presence.
"""
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'platform/core/src'))
from agent_platform.release_verify import Verifier  # noqa: E402
from lifecycle import is_fault_target  # noqa: E402

NAME, ZONE, POOL = 'agent-platform', 'us-east1-b', 'work'
DIGEST = re.compile(r'([a-z0-9-]+)@sha256:([0-9a-f]{64})')


def subprocess_runner(args, input=None):
    """Discard provider/tool stderr, which can contain private account/project details."""
    try:
        result = subprocess.run([str(a) for a in args], capture_output=True, text=True, input=input,
                                timeout=120, check=False)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ''


def required_secrets(docs):
    found = set()
    for doc in docs:
        if doc.get('kind') not in ('Deployment', 'StatefulSet', 'Job'):
            continue
        namespace, pod = doc['metadata']['namespace'], doc['spec']['template']['spec']
        for volume in pod.get('volumes', []):
            if 'secret' in volume and not volume['secret'].get('optional', False):
                found.add((namespace, volume['secret']['secretName']))
            for source in volume.get('projected', {}).get('sources', []):
                ref = source.get('secret')
                if ref and not ref.get('optional', False):
                    found.add((namespace, ref['name']))
        for container in pod.get('containers', []) + pod.get('initContainers', []):
            for env in container.get('env', []):
                ref = env.get('valueFrom', {}).get('secretKeyRef')
                if ref and not ref.get('optional', False):
                    found.add((namespace, ref['name']))
            for env in container.get('envFrom', []):
                ref = env.get('secretRef')
                if ref and not ref.get('optional', False):
                    found.add((namespace, ref['name']))
        found.update((namespace, ref['name']) for ref in pod.get('imagePullSecrets', []))
    return sorted(found)


def controlled_by(doc, uid):
    return any(r.get('controller') is True and r.get('uid') == uid
               for r in doc.get('metadata', {}).get('ownerReferences', []))


def image_matches(image_id, ref):
    if not isinstance(image_id, str) or not isinstance(ref, str):
        return False
    digest = ref.rsplit('@', 1)[-1]
    for prefix in ('docker-pullable://', 'containerd://', 'docker://'):
        image_id = image_id.removeprefix(prefix)
    return bool(re.fullmatch(r'sha256:[0-9a-f]{64}', digest)) and image_id.rsplit('@', 1)[-1] == digest


def workload_ready(expected, actual, items):
    """Ready status alone cannot prove the desired or running image. Check the ownership chain too."""
    try:
        desired = expected['spec'].get('replicas', 1)
        if not actual or type(desired) is not int or desired < 0 or (desired == 0 and not is_fault_target(expected)):
            return False
        status, meta = actual['status'], actual['metadata']
        if (meta.get('deletionTimestamp') or actual['spec'].get('replicas', 1) != desired
                or status.get('observedGeneration', 0) < meta['generation']
                or any(status.get(k, 0) != desired for k in ('replicas', 'updatedReplicas', 'readyReplicas'))):
            return False
        if expected['kind'] == 'Deployment' and status.get('availableReplicas', 0) != desired:
            return False
        if expected['kind'] == 'StatefulSet' and (not status.get('currentRevision')
                or status.get('currentRevision') != status.get('updateRevision')):
            return False
        images = {c['name']: c['image'] for c in expected['spec']['template']['spec']['containers']}
        if {c['name']: c['image'] for c in actual['spec']['template']['spec']['containers']} != images:
            return False
        init = {c['name']: c['image'] for c in expected['spec']['template']['spec'].get('initContainers', [])}
        if {c['name']: c['image'] for c in actual['spec']['template']['spec'].get('initContainers', [])} != init:
            return False
        owners = {meta['uid']}
        if expected['kind'] == 'Deployment':
            owners = {d['metadata']['uid'] for d in items if d['kind'] == 'ReplicaSet' and controlled_by(d, meta['uid'])}
        pods = [p for p in items if p['kind'] == 'Pod' and any(controlled_by(p, owner) for owner in owners)]
        if len(pods) != desired:
            return False
        for pod in pods:
            if (pod['metadata'].get('deletionTimestamp') or pod['status'].get('phase') != 'Running'
                    or not any(c['type'] == 'Ready' and c['status'] == 'True' for c in pod['status'].get('conditions', []))
                    or {c['name']: c['image'] for c in pod['spec']['containers']} != images):
                return False
            if (pod['spec'].get('ephemeralContainers') or
                    {c['name']: c['image'] for c in pod['spec'].get('initContainers', [])} != init):
                return False
            statuses = pod['status'].get('containerStatuses', [])
            if len(statuses) != len(images) or {c['name'] for c in statuses} != set(images):
                return False
            for container in statuses:
                if (not container.get('ready') or 'running' not in container.get('state', {})
                        or not image_matches(container.get('imageID', ''), images[container['name']])):
                    return False
            completed = pod['status'].get('initContainerStatuses', [])
            if {c['name'] for c in completed} != set(init) or len(completed) != len(init):
                return False
            for container in completed:
                if (container.get('state', {}).get('terminated', {}).get('exitCode') != 0
                        or not image_matches(container.get('imageID', ''), init[container['name']])):
                    return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


class Checker:
    def __init__(self, project, *, run=subprocess_runner, kubectl='kubectl', kubeconfig=None,
                 images=None, docs=(), out=print, cosign='cosign'):
        self.project, self.run, self.out = project, run, out
        self.kubectl = [kubectl] + (['--kubeconfig', str(kubeconfig)] if kubeconfig else [])
        self.images = images if images is not None else json.loads((HERE / 'release-rc1.lock.json').read_text())
        self.docs, self.failed = list(docs), 0
        self.verifier = Verifier(project, self.images.get('source_commit'), run, cosign=cosign)

    def line(self, ok, what, detail=''):
        self.failed += not ok
        text = ('PASS' if ok else 'FAIL') + '  ' + what + ('  (' + detail + ')' if detail else '')
        text = text.replace(self.project, '<project>') if self.project else text
        self.out(re.sub(r'\b\d{10,13}\b', '<number>', text))

    def gcloud(self, *args):
        return self.run(['gcloud', *args, '--project', self.project])

    def k(self, *args):
        return self.run(self.kubectl + list(args))

    def cluster(self):
        rc, raw = self.gcloud('container', 'clusters', 'describe', NAME, '--location', ZONE, '--format=json')
        try:
            described = json.loads(raw) if rc == 0 else {}
            running = described.get('status') == 'RUNNING'
            pool = any(p.get('name') == POOL for p in described.get('nodePools', []))
        except (ValueError, TypeError, AttributeError):
            running, pool = False, False
        self.line(running, 'cluster control plane running')
        rc, raw = self.gcloud('compute', 'instance-groups', 'managed', 'list',
            '--filter=name~gke-' + NAME + '-' + POOL, '--format=value(size)')
        sizes = [int(x) for x in raw.split() if x.isdigit()] if rc == 0 else []
        self.line(pool and bool(sizes) and sum(sizes) > 0, 'node pool has capacity')
        rc, raw = self.k('get', 'nodes', '-l', 'cloud.google.com/gke-nodepool=' + POOL, '-o', 'json')
        try:
            nodes = json.loads(raw)['items'] if rc == 0 else []
            ready = bool(nodes) and all(not n['spec'].get('unschedulable') and not n['metadata'].get('deletionTimestamp')
                and any(c['type'] == 'Ready' and c['status'] == 'True' for c in n['status'].get('conditions', [])) for n in nodes)
        except (ValueError, KeyError, TypeError):
            ready = False
        self.line(ready, 'node pool has ready schedulable nodes')

    def workloads(self):
        required = [d for d in self.docs if d['kind'] in ('Deployment', 'StatefulSet')]
        self.line(bool(required), 'selected release inventory available')
        groups = {}
        for namespace in sorted({d['metadata']['namespace'] for d in required}):
            rc, raw = self.k('-n', namespace, 'get', 'deployments,statefulsets,replicasets,pods', '-o', 'json')
            try:
                groups[namespace] = json.loads(raw)['items'] if rc == 0 else []
            except (ValueError, KeyError, TypeError):
                groups[namespace] = []
        for expected in required:
            namespace, name, kind = expected['metadata']['namespace'], expected['metadata']['name'], expected['kind']
            items = groups[namespace]
            found = [d for d in items if d.get('kind') == kind and d['metadata']['name'] == name]
            ok = len(found) == 1 and workload_ready(expected, found[0], items)
            state = 'ready on selected images' if expected['spec'].get('replicas', 1) else 'stopped as declared'
            self.line(ok, 'workload ' + namespace + '/' + name + ' ' + state)

    def secrets(self):
        names = required_secrets(self.docs)
        self.line(bool(names), 'required Secret references available')
        for namespace, name in names:
            rc, raw = self.k('-n', namespace, 'get', 'secret', name, '--ignore-not-found', '-o', 'name')
            self.line(rc == 0 and raw.strip() == 'secret/' + name, 'secret ' + namespace + '/' + name + ' exists')

    def all_images(self):
        self.line(bool(self.images['images']), 'release image inventory available')
        for name, ref in self.images['images'].items():
            found = DIGEST.fullmatch(ref or '')
            self.line(bool(found), 'image ' + name + ' pinned')
            if not found:
                continue
            full = self.images['registry'].replace('PROJECT_ID', self.project) + ref
            self.line(self.verifier.signature(full), 'image ' + name + ' signed by declared CI workflow')
            self.line(self.verifier.attestation(full), 'image ' + name + ' attested by declared KMS authority')
            if self.images.get('schema_version', 1) >= 2:
                declarations = self.images.get('provenance', {})
                entry = declarations.get(name, {}) if isinstance(declarations, dict) else {}
                self.line(self.verifier.provenance(full,
                    image=ref.split('@', 1)[0],
                    archive_sha256=entry.get('git_archive_sha256'),
                    input_fingerprint=entry.get('input_fingerprint'),
                    materials=entry.get('materials')),
                    'image ' + name + ' source and materials cryptographically attested')

    def all(self):
        rc, raw = self.run(['gcloud', 'auth', 'list', '--filter=status:ACTIVE', '--format=value(account)'])
        self.line(rc == 0 and bool(raw.strip()), 'gcloud active account')
        self.cluster()
        self.workloads()
        self.secrets()
        self.all_images()
        self.out(('%d check(s) failed' % self.failed) if self.failed else 'all checks passed')
        return int(bool(self.failed))


def main():
    sys.path.insert(0, str(HERE))
    import lifecycle
    import yaml
    try:
        project = lifecycle.settings()['project_id']
        kubeconfig = lifecycle.kubeconfig()
        docs = [d for d in yaml.safe_load_all(lifecycle.render_release()) if d]
    except (SystemExit, OSError, ValueError, KeyError):
        raise SystemExit('FAIL  selected release or cluster access unavailable') from None
    checker = Checker(project, kubectl=lifecycle.KUBECTL, kubeconfig=kubeconfig, docs=docs)
    raise SystemExit(checker.all())


if __name__ == '__main__':
    main()
