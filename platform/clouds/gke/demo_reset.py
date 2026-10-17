#!/usr/bin/env python3
"""`make demo-reset`: put an UP platform into a clean demo state, right before recording. Owner identity; asks first.

Refuses unless the cluster has a node and the front door, the redactor and the ops agent are ready. Then, after the
owner types "yes":

  1. fault-demo: the declared manifest is applied again (no fault, 0 replicas), as `make up` does for that one Deployment
  2. ops agent: rollout restart, which clears its in-memory proposals, timeline and denials (nothing else holds them)
  3. demo data: the Financial Agent's demo user gets the synthetic Sep/Oct 2026 seed again (`make seed-demo`)
  4. redactor warm-up: one redaction of a fixed sentence with no user data, from inside the front-door Pod with its own
     client key (the key is read inside the Pod and never leaves it), so the first live question does not wait on DLP
     If that exec is refused, nothing else is tried: it says so and asks the owner to ask one non-personal question instead
  5. prints the port-forward commands for 8080 (console) and 8081 (Financial Agent)

It never reads, writes or rotates a Secret, never touches the approval passphrase, and prints no secret value or project ID.
"""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
READY = (('apps', 'app'), ('platform', 'redactor'), ('ops', 'ops-agent'))
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


class Reset:
    def __init__(self, *, kubectl, nodes, render_fault_demo, seed, ask=input, out=print):
        """kubectl(*args, input=None) -> (returncode, stdout); nodes() -> int or None; render_fault_demo() -> YAML text of
        the declared fault-demo Deployment; seed() runs `make seed-demo`'s step."""
        self.kubectl, self.nodes, self.render_fault_demo, self.seed = kubectl, nodes, render_fault_demo, seed
        self.ask, self.out = ask, out

    def ready(self, namespace, name):
        rc, out = self.kubectl('-n', namespace, 'get', 'deployment', name, '-o', 'jsonpath={.status.readyReplicas}')
        return rc == 0 and out.strip().isdigit() and int(out.strip()) >= 1

    def check_up(self):
        nodes = self.nodes()
        if not nodes:
            raise Refused('demo-reset: the platform is down (0 nodes). Run make up first.')
        missing = [ns + '/' + name for ns, name in READY if not self.ready(ns, name)]
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
                  '--force-conflicts', '-f', '-', input=self.render_fault_demo())
        self.step('fault-demo: rolled out', '-n', 'apps', 'rollout', 'status', 'deployment/fault-demo', '--timeout=180s')
        self.step('ops agent: restarted (in-memory proposals cleared)', '-n', 'ops', 'rollout', 'restart', 'deployment/ops-agent')
        self.step('ops agent: ready', '-n', 'ops', 'rollout', 'status', 'deployment/ops-agent', '--timeout=300s')
        self.seed()
        self.out('done   demo data: demo user re-seeded')
        rc, out = self.kubectl('-n', 'apps', 'exec', 'deployment/app', '-c', 'app', '--', '/usr/local/bin/python3.12', '-c', WARM_UP)
        if rc == 0 and 'redactor warm-up: ok' in out:
            self.out('done   redactor warm-up (one call, no user data)')
        else:  # e.g. exec refused by a policy: never retried another way; the owner warms DLP through the product instead
            self.out('FAILED redactor warm-up (kubectl exec was refused or failed; nothing was bypassed).')
            self.out('       Instead: ask one non-personal question in the console before recording, for example')
            self.out('       "How much did I spend in October 2026?" on http://127.0.0.1:8081/.')
        self.out('')
        self.out('Port-forwards (one terminal each):')
        for line in PORT_FORWARDS:
            self.out('  ' + line)
        return 0


def main():
    sys.path.insert(0, str(HERE))
    import lifecycle
    import yaml

    def kubectl(*args, input=None):
        result = lifecycle.kubectl(*args, check=False, capture=True, input=input)
        return result.returncode, result.stdout

    def nodes():
        s = lifecycle.settings()
        result = lifecycle.run('gcloud', 'compute', 'instance-groups', 'managed', 'list', '--project', s['project_id'],
                               '--filter=name~gke-' + lifecycle.NAME + '-' + lifecycle.POOL, '--format=value(size)', capture=True, check=False)
        sizes = [int(x) for x in result.stdout.split() if x.isdigit()]
        return sum(sizes) if result.returncode == 0 and sizes else None

    def render_fault_demo():
        o = lifecycle.outputs()
        rendered = lifecycle.run(sys.executable, '-B', HERE / 'render.py', '--project-id', o['project_id'], '--control-plane-cidr',
                                 o['control_plane_cidr'], '--gateway-gsa', o['gateway_gsa'], '--redactor-gsa', o['redactor_gsa'],
                                 '--kubectl', lifecycle.KUBECTL, capture=True).stdout
        docs = [d for d in yaml.safe_load_all(rendered) if d and d['kind'] == 'Deployment'
                and d['metadata'].get('namespace') == 'apps' and d['metadata']['name'] == 'fault-demo']
        if len(docs) != 1:
            raise Refused('demo-reset: fault-demo not found in the rendered manifests')
        return yaml.safe_dump_all(docs)

    lifecycle.kubeconfig()
    try:
        code = Reset(kubectl=kubectl, nodes=nodes, render_fault_demo=render_fault_demo, seed=lifecycle.seed_demo).run()
    except Refused as refused:
        print(refused.code)
        code = 2
    raise SystemExit(code)


if __name__ == '__main__':
    main()
