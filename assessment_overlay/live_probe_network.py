"""K01: Pod-origin TCP matrix over the disposable cluster's actual CNI."""
import json

from live_probe_kube import one_pod, python_probe


MATRIX = {
    'financial': ('agent-financial', 'agent-platform/user-slot=u1', (
        ('boundary', 'gateway-boundary.platform.svc.cluster.local', 4000, True),
        ('redactor', 'redactor.platform.svc.cluster.local', 4003, True),
        ('broker', 'financial-frontdoor.apps.svc.cluster.local', 8082, True),
        ('postgres', 'postgres.platform.svc.cluster.local', 5432, False),
        ('stub', 'provider-stub.assess-probes.svc.cluster.local', 8080, False))),
    'app': ('apps', 'app.kubernetes.io/name=app', (
        ('postgres', 'postgres.platform.svc.cluster.local', 5432, True),
        ('stub', 'provider-stub.assess-probes.svc.cluster.local', 8080, False))),
    'ops': ('ops', 'app.kubernetes.io/name=ops-agent', (
        ('executor', 'ops-executor.ops.svc.cluster.local', 8091, True),
        ('postgres', 'postgres.platform.svc.cluster.local', 5432, False))),
    'boundary': ('platform', 'app.kubernetes.io/name=gateway-boundary', (
        ('private_gateway', 'gateway-provider.platform.svc.cluster.local', 4001, True),
        ('postgres', 'postgres.platform.svc.cluster.local', 5432, False))),
}


SCRIPT = r'''
import json, socket
checks = {}
for name, host, port, expected in __TARGETS__:
    try:
        connection = socket.create_connection((host, port), timeout=3)
        connection.close()
        connected = True
    except OSError:
        connected = False
    checks[name] = connected == expected
print(json.dumps(checks))
'''


def probe_k01(kubeconfig, *, executable='kubectl', pod=one_pod, execute=python_probe):
    checks = {}
    for source, (namespace, selector, targets) in MATRIX.items():
        name = pod(kubeconfig, namespace, selector, executable=executable)
        script = SCRIPT.replace('__TARGETS__', json.dumps(targets))
        result = execute(kubeconfig, namespace, name, script, executable=executable)
        if set(result) != {target[0] for target in targets}:
            raise RuntimeError('assessment:network_matrix_incomplete')
        checks.update({source + '_' + target: allowed for target, allowed in result.items()})
    return checks
