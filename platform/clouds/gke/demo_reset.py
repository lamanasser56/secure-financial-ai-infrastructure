#!/usr/bin/env python3
"""`make demo-reset`: put an UP platform into a clean demo state, right before recording. Owner identity; asks first.

Refuses unless the cluster has a node and every released service and worker is ready. Then, after the
owner types "yes":

  1. fault-demo: the declared manifest is applied again (no fault, 0 replicas), as `make up` does for that one Deployment
  2. ops agent: rollout restart, which clears its in-memory proposals, timeline and denials (nothing else holds them)
  3. demo data: the Financial Agent's demo user gets the synthetic Sep/Oct 2026 seed again (`make seed-demo`)
  4. redactor warm-up: one redaction of a fixed sentence with no user data, from inside the front-door Pod with its own
     client key (the key is read inside the Pod and never leaves it), so the first live question does not wait on DLP
     If that exec is refused, nothing else is tried and reset reports incomplete with a nonzero exit status.
  5. prints the port-forward commands for 8080 (console) and 8081 (Financial Agent)

It never reads, writes or rotates a Secret, never touches the approval passphrase, and prints no secret value or project ID.
"""
import json
from pathlib import Path
import sys

import yaml

HERE = Path(__file__).resolve().parent
WARM_UP_TEXT = 'Demo warm-up sentence with no personal data.'
# Runs inside the front-door Pod: its own redactor client key, the same client the app uses. Prints only closed text.
WARM_UP = ("import json; from agent_platform.redaction import RedactorClient; "
           "c = json.load(open('/secrets/app/app.json')); "
           "RedactorClient('http://redactor.platform.svc.cluster.local:4003', c['redactor_key'], timeout=60).redact(%r); "
           "print('redactor warm-up: ok')" % WARM_UP_TEXT)
PORT_FORWARDS = ('make port-forward                # console:          http://127.0.0.1:8080/',
                 'make agent-forward A=financial   # Financial Agent:  http://127.0.0.1:8081/')


class Refused(SystemExit):
    pass


def declared_state(rendered):
    """Use the release's own workload inventory, excluding the intentionally stopped fault demonstration."""
    docs = [d for d in yaml.safe_load_all(rendered) if d]
    fault = [d for d in docs if d['kind'] == 'Deployment'
             and d['metadata'].get('namespace') == 'apps' and d['metadata']['name'] == 'fault-demo']
    if len(fault) != 1 or fault[0]['spec'].get('replicas') != 0:
        raise Refused('demo-reset: release must declare one stopped fault-demo Deployment')
    required = [(d['kind'].lower(), d['metadata']['namespace'], d['metadata']['name']) for d in docs
                if d['kind'] in ('Deployment', 'StatefulSet') and d not in fault]
    if not required:
        raise Refused('demo-reset: release workload inventory is empty')
    return yaml.safe_dump_all(fault), required


class Reset:
    def __init__(self, *, kubectl, nodes, declared, seed, ask=input, out=print):
        """kubectl(*args, input=None) -> (returncode, stdout); nodes() -> int or None;
        declared is the fault manifest and required workloads from declared_state; seed() runs the demo seed step."""
        self.kubectl, self.nodes, self.declared, self.seed = kubectl, nodes, declared, seed
        self.ask, self.out = ask, out

    def ready(self, kind, namespace, name):
        rc, out = self.kubectl('-n', namespace, 'get', kind, name, '-o',
                               'jsonpath={.spec.replicas} {.status.readyReplicas} {.status.updatedReplicas} '
                               '{.metadata.generation} {.status.observedGeneration}')
        parts = out.split()
        if rc != 0 or len(parts) != 5 or not all(part.isdigit() for part in parts):
            return False
        desired, ready, updated, generation, observed = map(int, parts)
        return desired > 0 and ready == updated == desired and generation == observed

    def check_up(self):
        nodes = self.nodes()
        if not nodes:
            raise Refused('demo-reset: the platform is down (0 nodes). Run make up first.')
        missing = [ns + '/' + name for kind, ns, name in self.declared[1] if not self.ready(kind, ns, name)]
        if missing:
            raise Refused('demo-reset: not ready yet: ' + ', '.join(missing) + '. Wait for make up to finish.')

    def step(self, what, *args, input=None):
        rc, _ = self.kubectl(*args, input=input)
        self.out(('done   ' if rc == 0 else 'FAILED ') + what)
        if rc != 0:
            raise Refused('demo-reset: stopped at: ' + what)

    def run(self):
        self.check_up()
        self.out('demo-reset will: reset fault-demo; restart the ops agent (clears its proposals); re-seed the demo user;')
        self.out('warm up the redactor once (no user data). Secrets and the passphrase are not touched.')
        if self.ask('Type yes to continue: ').strip() != 'yes':
            raise Refused('demo-reset: nothing changed.')
        self.step('fault-demo: declared manifest applied (no fault, 0 replicas)', 'apply', '--server-side', '--field-manager=agent-platform',
                  '--force-conflicts', '-f', '-', input=self.declared[0])
        self.step('fault-demo: rolled out', '-n', 'apps', 'rollout', 'status', 'deployment/fault-demo', '--timeout=180s')
        self.step('ops agent: restarted (in-memory proposals cleared)', '-n', 'ops', 'rollout', 'restart', 'deployment/ops-agent')
        self.step('ops agent: ready', '-n', 'ops', 'rollout', 'status', 'deployment/ops-agent', '--timeout=300s')
        self.seed()
        self.out('done   demo data: demo user re-seeded')
        rc, out = self.kubectl('-n', 'apps', 'exec', 'deployment/app', '-c', 'app', '--', '/usr/local/bin/python3.12', '-c', WARM_UP)
        if rc == 0 and 'redactor warm-up: ok' in out:
            self.out('done   redactor warm-up (one call, no user data)')
        else:  # one supported route only; incomplete reset must not be reported as a successful recording preparation
            self.out('FAILED redactor warm-up (kubectl exec was refused or failed; nothing was bypassed).')
            raise Refused('demo-reset: incomplete: redactor warm-up failed; correct the failure and repeat reset.')
        self.out('')
        self.out('Port-forwards (one terminal each):')
        for line in PORT_FORWARDS:
            self.out('  ' + line)
        return 0


def main():
    sys.path.insert(0, str(HERE))
    import lifecycle

    def kubectl(*args, input=None):
        result = lifecycle.kubectl(*args, check=False, capture=True, input=input)
        return result.returncode, result.stdout

    def nodes():
        s = lifecycle.settings()
        result = lifecycle.run('gcloud', 'compute', 'instance-groups', 'managed', 'list', '--project', s['project_id'],
                               '--filter=name~gke-' + lifecycle.NAME + '-' + lifecycle.POOL, '--format=value(size)', capture=True, check=False)
        sizes = [int(x) for x in result.stdout.split() if x.isdigit()]
        return sum(sizes) if result.returncode == 0 and sizes else None

    lifecycle.kubeconfig()
    try:
        code = Reset(kubectl=kubectl, nodes=nodes, declared=declared_state(lifecycle.render_release()),
                     seed=lifecycle.seed_demo).run()
    except Refused as refused:
        print(refused.code)
        code = 2
    raise SystemExit(code)


if __name__ == '__main__':
    main()
