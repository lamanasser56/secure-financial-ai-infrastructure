#!/usr/bin/env python3
"""`make demo-check`: read-only readiness checks before a live session. One PASS/FAIL line per check, exit 1 on any FAIL.

Reads only (gcloud describe/list, kubectl get, Secret entry names). It never prints a secret value, an account name or the
project ID: every line is built from closed text, and anything printed passes a final mask of the project ID.

  gcloud auth and the kubectl context work
  cluster status RUNNING; node pool size (0 = down, which is expected before `make up`)
  every image in images.json is pinned (no PENDING_CI) and its digest is keyless-signed (cosign .sig tag) and attested
    by the CI attestor (Binary Authorization)
  the platform and agent Secrets exist (names only)
  hello leftovers: namespace agent-hello, NetworkPolicies agent-hello-to-gateway / -to-redactor, key alias agent-hello
    in Secrets platform/bootstrap and platform/redactor (docs/operations/hello-retirement-cleanup.md)
"""
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
NAME, ZONE, POOL = 'agent-platform', 'us-east1-b', 'work'
ATTESTOR = NAME + '-ci'
DIGEST = re.compile(r'([a-z0-9-]+)@sha256:([0-9a-f]{64})')
PLATFORM_SECRETS = (('platform', 'postgres'), ('platform', 'gateway'), ('platform', 'redactor'), ('platform', 'bootstrap'),
                    ('apps', 'app'), ('ops', 'ops-agent'))
HELLO = 'agent-hello'


def subprocess_runner(args, input=None):
    """(returncode, stdout). stderr is discarded: gcloud and kubectl errors can contain the project ID."""
    try:
        result = subprocess.run([str(a) for a in args], capture_output=True, text=True, input=input, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return 127, ''
    return result.returncode, result.stdout


class Checker:
    def __init__(self, project, *, run=subprocess_runner, kubectl='kubectl', kubeconfig=None, images=None, agents=(), out=print):
        self.project, self.run, self.out = project, run, out
        self.kubectl = [kubectl] + (['--kubeconfig', str(kubeconfig)] if kubeconfig else [])
        self.images = images if images is not None else json.loads((HERE / 'images.json').read_text())
        self.agents = tuple(agents)
        self.failed = 0

    def line(self, ok, what, detail=''):
        if not ok:
            self.failed += 1
        text = ('PASS' if ok else 'FAIL') + '  ' + what + ('  (' + detail + ')' if detail else '')
        self.out(text.replace(self.project, '<project>') if self.project else text)  # last line of defence

    def gcloud(self, *args):
        return self.run(['gcloud', *args, '--project', self.project])

    def k(self, *args):
        return self.run(self.kubectl + list(args))

    # -- access ---------------------------------------------------------------------------------------------
    def auth(self):
        rc, out = self.run(['gcloud', 'auth', 'list', '--filter=status:ACTIVE', '--format=value(account)'])
        self.line(rc == 0 and bool(out.strip()), 'gcloud: an active account')
        rc, out = self.run(['gcloud', 'auth', 'print-access-token', '--quiet'])
        self.line(rc == 0 and bool(out.strip()), 'gcloud: a fresh access token (not printed)')

    def cluster(self):
        rc, out = self.gcloud('container', 'clusters', 'describe', NAME, '--location', ZONE, '--format=json')
        try:
            described = json.loads(out) if rc == 0 else {}
        except ValueError:
            described = {}
        status = described.get('status')
        self.line(status == 'RUNNING', 'cluster ' + NAME + ' status', str(status or 'unreadable'))
        pool = next((p for p in described.get('nodePools') or [] if p.get('name') == POOL), None)
        rc, out = self.gcloud('compute', 'instance-groups', 'managed', 'list', '--filter=name~gke-' + NAME + '-' + POOL,
                              '--format=value(size)')
        sizes = [int(x) for x in out.split() if x.isdigit()] if rc == 0 else []
        nodes = sum(sizes) if sizes else None
        self.line(pool is not None and nodes is not None, 'node pool ' + POOL + ' size',
                  ('%d node(s)' % nodes + (', platform is down (run make up)' if nodes == 0 else '')) if nodes is not None else 'unreadable')
        return status == 'RUNNING'

    def context(self):
        rc, out = self.k('get', 'namespace', 'platform', '-o', 'name')
        ok = rc == 0 and out.strip() == 'namespace/platform'
        self.line(ok, 'kubectl: context reaches the cluster API')
        return ok

    # -- images ---------------------------------------------------------------------------------------------
    def image(self, name, ref):
        found = DIGEST.fullmatch(ref or '')
        if not found:
            self.line(False, 'image ' + name + ' pinned', 'not a digest: ' + ('PENDING_CI' if ref == 'PENDING_CI' else 'unexpected value'))
            return
        repo_image, digest = found.group(1), found.group(2)
        short = 'sha256:' + digest[:4] + '…' + digest[-4:]
        self.line(True, 'image ' + name + ' pinned', short)
        base = self.images['registry'].replace('PROJECT_ID', self.project) + repo_image
        rc, out = self.gcloud('artifacts', 'docker', 'tags', 'list', base, '--format=value(tag)')
        tags = {t.rsplit('/', 1)[-1] for t in out.split()} if rc == 0 else set()
        self.line('sha256-' + digest + '.sig' in tags, 'image ' + name + ' signed (cosign signature present)',
                  short if rc == 0 else 'registry unreadable')
        rc, out = self.gcloud('container', 'binauthz', 'attestations', 'list', '--attestor', ATTESTOR,
                              '--artifact-url', base + '@sha256:' + digest, '--format=value(name)')
        count = len(out.split()) if rc == 0 else None
        self.line(bool(count), 'image ' + name + ' attested by ' + ATTESTOR, short if count is not None else 'attestations unreadable')

    def all_images(self):
        for name, ref in self.images['images'].items():
            self.image(name, ref)

    # -- cluster objects (names only) -----------------------------------------------------------------------
    def exists(self, namespace, kind, name):
        rc, out = self.k('-n', namespace, 'get', kind, name, '--ignore-not-found', '-o', 'name') if namespace else \
            self.k('get', kind, name, '--ignore-not-found', '-o', 'name')
        return None if rc != 0 else bool(out.strip())

    def secret_names(self):
        for namespace, name in PLATFORM_SECRETS + tuple(('agent-' + a, 'agent') for a in self.agents):
            present = self.exists(namespace, 'secret', name)
            self.line(present is True, 'secret ' + namespace + '/' + name + ' exists', 'unreadable' if present is None else '')

    def entry_names(self, namespace, name, key):
        """The top-level names inside one Secret's JSON entry (aliases), never the values."""
        rc, out = self.k('-n', namespace, 'get', 'secret', name, '-o', 'json', '--ignore-not-found')
        if rc != 0 or not out.strip():
            return None
        import base64
        try:
            value = json.loads(base64.b64decode(json.loads(out)['data'][key]))
        except (ValueError, KeyError, TypeError):
            return None
        if key == 'bootstrap.json':
            return {k.get('alias') for k in value.get('virtual_keys') or [] if isinstance(k, dict)}
        return set(value)

    def hello(self):
        ns = self.exists(None, 'namespace', HELLO)
        self.line(ns is False, 'hello: namespace ' + HELLO + ' gone', 'still present' if ns else 'unreadable' if ns is None else '')
        for policy in (HELLO + '-to-gateway', HELLO + '-to-redactor'):
            present = self.exists('platform', 'networkpolicy', policy)
            self.line(present is False, 'hello: NetworkPolicy platform/' + policy + ' gone',
                      'still present' if present else 'unreadable' if present is None else '')
        for namespace, name, key, label in (('platform', 'bootstrap', 'bootstrap.json', 'gateway key alias'),
                                            ('platform', 'redactor', 'clients.json', 'redactor client key')):
            names = self.entry_names(namespace, name, key)
            self.line(names is not None and HELLO not in names, 'hello: ' + label + ' ' + HELLO + ' gone (secret ' + namespace + '/' + name + ')',
                      'unreadable' if names is None else 'still present: run --retire-agent hello' if HELLO in names else '')

    def all(self):
        self.auth()
        self.cluster()
        if self.context():
            self.secret_names()
            self.hello()
        else:
            self.line(False, 'secrets and hello leftovers', 'skipped: no cluster API access')
        self.all_images()
        self.out(('%d check(s) failed' % self.failed) if self.failed else 'all checks passed')
        return 1 if self.failed else 0


def main():
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(REPO / 'platform/core/src'))
    import lifecycle
    from agent_platform import onboarding
    project = lifecycle.settings()['project_id']
    try:
        kubeconfig = lifecycle.kubeconfig()  # local file only (gcloud describe + an exec credential helper)
    except SystemExit:
        kubeconfig = None
    checker = Checker(project, kubectl=lifecycle.KUBECTL, kubeconfig=kubeconfig, agents=onboarding.namespace_agents(onboarding.load_all()))
    raise SystemExit(checker.all())


if __name__ == '__main__':
    main()
