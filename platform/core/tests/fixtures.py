"""Shared offline fixtures: Kubernetes objects and a fake API client (no network)."""
import copy

from agent_platform.k8s import KubeError
from agent_platform.ops.registry import parse

GOOD = 'reg/app@sha256:' + 'a' * 64
BAD = 'reg/unsigned@sha256:' + 'b' * 64

REGISTRY = parse({'apps.fault-demo.min': '0', 'apps.fault-demo.max': '3', 'apps.fault-demo.images': GOOD, 'apps.fault-demo.health': 'none',
                  'platform.gateway.min': '1', 'platform.gateway.max': '1', 'platform.gateway.images': 'reg/gw@sha256:' + 'c' * 64,
                  'platform.gateway.health': 'http://gateway.platform.svc.cluster.local:4000/health/liveliness'})


def template(image=GOOD, env='none', memory='64Mi'):
    return {'metadata': {'labels': {'app.kubernetes.io/name': 'fault-demo'}},
            'spec': {'serviceAccountName': 'fault-demo', 'automountServiceAccountToken': False,
                     'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532},
                     'containers': [{'name': 'workload', 'image': image, 'env': [{'name': 'FAULT_MODE', 'value': env}],
                                     'resources': {'limits': {'memory': memory}},
                                     'securityContext': {'allowPrivilegeEscalation': False}}]}}


def deployment(revision=2, tmpl=None, replicas=1, available=1, generation=2, observed=2):
    return {'metadata': {'name': 'fault-demo', 'namespace': 'apps', 'uid': 'uid-1', 'generation': generation,
                         'annotations': {'deployment.kubernetes.io/revision': str(revision)}},
            'spec': {'replicas': replicas, 'selector': {'matchLabels': {'app.kubernetes.io/name': 'fault-demo'}},
                     'template': tmpl or template(env='crashloop')},
            'status': {'observedGeneration': observed, 'replicas': replicas, 'updatedReplicas': available,
                       'availableReplicas': available}}


def replicaset(revision, tmpl, uid='uid-1'):
    t = copy.deepcopy(tmpl)
    t['metadata']['labels']['pod-template-hash'] = 'h' + str(revision)
    return {'metadata': {'name': 'fault-demo-h' + str(revision), 'annotations': {'deployment.kubernetes.io/revision': str(revision)},
                         'ownerReferences': [{'kind': 'Deployment', 'uid': uid}]}, 'spec': {'template': t}}


def pod(name='fault-demo-1', waiting=None, last=None, ready=True, phase='Running', restarts=0):
    status = {'name': 'workload', 'ready': ready, 'restartCount': restarts,
              'state': {'waiting': {'reason': waiting}} if waiting else {'running': {}}}
    if last:
        status['lastState'] = {'terminated': {'reason': last}}
    return {'metadata': {'name': name}, 'status': {'phase': phase, 'containerStatuses': [status]}}


class FakeClient:
    def __init__(self, deployment, pods=(), events=(), replicasets=(), patch_error=None, after_patch=None):
        self.deployment, self.pods, self.events, self.replicasets = deployment, list(pods), list(events), list(replicasets)
        self.patches, self.patch_error, self.after_patch = [], patch_error, after_patch

    def get(self, kind, namespace, name):
        assert kind == 'deployments'
        return copy.deepcopy(self.deployment)

    def list(self, kind, namespace, selector=None):
        return copy.deepcopy({'pods': self.pods, 'events': self.events, 'replicasets': self.replicasets}.get(kind, []))

    def patch_deployment(self, namespace, name, patch):
        self.patches.append((namespace, name, patch))
        if self.patch_error:
            raise KubeError(*self.patch_error)
        if self.after_patch:
            self.deployment = self.after_patch(self.deployment, patch)
        return self.deployment
