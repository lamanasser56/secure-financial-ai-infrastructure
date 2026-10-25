"""Console data API (read-only, front door, loopback :8080): what the platform console screens show.

GET /api/console/topology           what exists and which paths are open or denied (sanitized facts from the selected final release render)
GET /api/console/agents             manifest facts + live state (pods, restarts, running image digest) per agent
GET /api/console/onboarding/<agent> the eight guarantees, each "verified" (seen live, with its source) or "declared"
GET /api/console/activity?limit=3   latest blocked / masked / approved events
GET /api/console/explain/<topic>    {title, plain, how, proof, without, file}; proof is live or null, never static text
GET /api/console/attacks            the latest attack-suite results file (closed fields), or {available: false}
GET /api/console/example            the rejected-agent example manifest (shipped file) and the command that checks it

The same handler serves the console UI (platform/core/ui): fixed files only, same-origin, no CDN.

Live facts come only from sources the front door already reads: the ops agent's read-only API (the bearer key the front
door already holds) and this process's own audit stream. The front door gets no Kubernetes token, no gateway key and no
new permission. Every value is a bounded closed field; nothing a model or a user wrote is returned.
"""
import ipaddress
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlsplit

import yaml

from agent_platform import audit, release_facts
from runtime.agents import web

HERE = Path(__file__).resolve()
NAME = re.compile(r'[a-z][a-z0-9-]{1,20}[a-z0-9]')
GUARANTEES = ('namespace', 'network', 'model_key', 'budget', 'redaction', 'tools', 'image', 'ops')
FRESH_SECONDS = 120  # the ops agent scans every 15 s; a finding older than this is not "live"
MAX_EVENTS = 20
ASSET_TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
               '.woff2': 'font/woff2'}
OPS = 'ops-agent'  # the Security & Operations Agent: a platform tenant (ops namespace), not onboarded from an agent.yaml
OPS_GUARANTEES = ('namespace', 'network', 'model_key', 'budget', 'redaction', 'approval', 'image')
REDACTION_RECENT_SECONDS = 3600  # how recent a redactor event for the agent's own key must be to count as seen


def locate_extras():
    """(UI dir, examples dir): side by side under /app/platform in the image; under platform/core/ui and docs/ in the repository."""
    image = HERE.parents[2]
    if (image / 'agents').is_dir():
        return image / 'ui', image / 'examples'
    return HERE.parents[2] / 'ui', HERE.parents[4] / 'docs/examples'


def display(name):
    return ' '.join(w[:1].upper() + w[1:] for w in name.split('-'))


def peer_names(rule):
    """Destination Services of one egress rule as [(namespace, app, port)], or ('ip', cidr) for an ipBlock."""
    found = []
    for peer in rule.get('to') or []:
        if 'ipBlock' in peer:
            found.append(('ip', peer['ipBlock'].get('cidr'), None))
            continue
        namespace = ((peer.get('namespaceSelector') or {}).get('matchLabels') or {}).get('kubernetes.io/metadata.name')
        app = ((peer.get('podSelector') or {}).get('matchLabels') or {}).get('app.kubernetes.io/name')
        for port in rule.get('ports') or [{}]:
            found.append((namespace, app, port.get('port')))
    return found


class Console:
    def __init__(self, ops, *, extras=None, clock=time.time, recent_audit=audit.recent,
                 live_attacks=Path('/attack-results/attack-suite.json'), facts=None, facts_path=release_facts.MOUNT):
        """`ops(path)` GETs the ops agent's read-only API and returns the decoded JSON (raises when it is unreachable)."""
        self._ops, self._clock, self._recent_audit = ops, clock, recent_audit
        if facts is not None:
            self.facts = release_facts.validate(facts)
        elif Path(facts_path).is_file():
            self.facts = release_facts.load(facts_path)
        elif (HERE.parents[2] / 'agents').is_dir():
            raise ValueError('mounted release facts required')
        else:
            self.facts = release_facts.repository()
        self.source_commit = self.facts['source_commit']
        self.ui_dir, self.examples_dir = extras or locate_extras()
        self.live_attacks = Path(live_attacks)  # the mounted ConfigMap apps/attack-results (optional)
        self._cache = {}
        self._manifests = self._load_manifests()
        self._opscfg = self._load_ops()

    # manifests ---------------------------------------------------------------------------------------------
    def _load_manifests(self):
        found = {}
        for name, manifest in sorted(self.facts['agents'].items()):
            ns = 'agent-' + name
            rendered = [d for d in self.facts['documents'] if d['metadata'].get('namespace') == ns
                        or (d['kind'] == 'Namespace' and d['metadata']['name'] == ns)]
            if NAME.fullmatch(name) and rendered:
                found[name] = {'manifest': manifest, 'rendered': rendered,
                               'file': f'platform/core/kubernetes/agents/{name}.yaml'}
        return found

    def _load_ops(self):
        from agent_platform.ops import registry
        docs = self.facts['documents']
        deployment = self._kind(docs, 'Deployment', OPS)
        config = self._kind(docs, 'ConfigMap', 'ops-agent-registry')
        if deployment is None or config is None:
            return None
        policies = [d for d in docs if d['kind'] == 'NetworkPolicy' and d['metadata'].get('namespace') == 'ops']
        observed = self._kind(docs, 'ConfigMap', 'ops-agent-observe')
        return {'deployment': deployment, 'targets': registry.parse(config['data']), 'rendered': policies,
                'observed': sorted((observed or {}).get('data') or {}), 'policy_names': (OPS, 'ops-agent-apiserver'),
                'file': 'platform/core/kubernetes/ops/workloads.yaml'}

    def _model(self):
        return self.facts['model']

    @staticmethod
    def _kind(rendered, kind, name=None):
        return next((d for d in rendered if d.get('kind') == kind and (name is None or d['metadata']['name'] == name)), None)

    def _egress(self, entry):
        found = []
        for name in entry.get('policy_names', ('agent',)):
            policy = self._kind(entry['rendered'], 'NetworkPolicy', name)
            for rule in (policy or {}).get('spec', {}).get('egress') or []:
                found += peer_names(rule)
        return found

    @staticmethod
    def _runtime(command):
        version = re.search(r'python(3\.\d+)', command)
        return 'node' if command.endswith('/node') else ('python ' + version.group(1) if version else None)

    # live sources -------------------------------------------------------------------------------------------
    def _live(self, path):
        """The ops agent's answer, cached for 3 s so a polling console cannot multiply Kubernetes reads. None if unreachable."""
        now = self._clock()
        hit = self._cache.get(path)
        if hit and now - hit[0] < 3:
            return hit[1]
        try:
            value = self._ops(path)
        except Exception:
            value = None
        self._cache[path] = (now, value)
        return value

    def _finding(self, target):
        snapshot = self._live('/v1/snapshot')
        findings = (snapshot or {}).get('findings') or {}
        ns, _, workload = target.partition('.')
        entry = self._manifests.get(ns.removeprefix('agent-')) if ns.startswith('agent-') and workload == 'agent' else None
        workers = [d for d in (entry or {}).get('rendered', []) if d['kind'] == 'Deployment']
        if not workers or [d['metadata']['name'] for d in workers] == [workload]:
            finding = findings.get(target)
            return finding if type(finding) is dict and type(finding.get('facts')) is dict else None
        parts, desired = [], 0
        for worker in workers:
            part = findings.get(ns + '.' + worker['metadata']['name'])
            valid = type(part) is dict and type(part.get('facts')) is dict
            desired += part['desired_replicas'] if valid else max(1, worker['spec'].get('replicas', 1))
            if valid:
                parts.append(part)
        if not parts:
            return None
        return {'namespace': ns, 'deployment': 'agent',
                'finding': 'HEALTHY' if len(parts) == len(workers) and all(p['finding'] == 'HEALTHY' for p in parts) else 'DEGRADED',
                'desired_replicas': desired,
                'facts': {**{key: sum(p['facts'].get(key, 0) for p in parts)
                             for key in ('pods_ready', 'pods_total', 'restarts')},
                          'observed_at': min(p['facts'].get('observed_at', 0) for p in parts),
                          'image_digests': sorted({image for p in parts for image in p['facts'].get('image_digests', [])})}}

    def _fresh(self, finding):
        return finding is not None and self._clock() - finding['facts'].get('observed_at', 0) <= FRESH_SECONDS

    def _live_block(self, name):
        finding = self._finding(f'agent-{name}.agent')
        if not self._fresh(finding):
            return None
        f = finding['facts']
        return {'source': 'ops-agent /v1/snapshot', 'observed_at': f['observed_at'], 'state': finding['finding'],
                'pods_ready': f['pods_ready'], 'pods_total': f['pods_total'], 'desired': finding['desired_replicas'],
                'restarts': f['restarts'], 'image_digests': f['image_digests']}

    # agents -------------------------------------------------------------------------------------------------
    def _health(self, name):
        """Live workload health: running | not_ready | absent, or None when the live source cannot say (ops unreachable or stale)."""
        snapshot = self._live('/v1/snapshot')
        if snapshot is None:
            return None
        finding = self._finding(f'agent-{name}.agent')
        if finding is not None and not self._fresh(finding):
            return None
        live = self._live_block(name)
        if live is None:
            state = 'absent'  # the ops agent answered and has no scan of this workload
        elif live['pods_ready'] >= 1 and live['pods_ready'] >= live['desired']:
            state = 'running'
        elif live['pods_total'] >= 1:
            state = 'not_ready'
        else:
            state = 'absent'
        return {'state': state, 'source': 'ops-agent /v1/snapshot'}

    def _agent(self, name):
        entry = self._manifests[name]
        m = entry['manifest']
        runtime = self._runtime((m['runtime']['command'] or [''])[0])
        data = m['data']
        return {'id': name, 'name': name, 'node': 'agent-' + name, 'kind': 'agent', 'display': display(name), 'namespace': 'agent-' + name, 'team': m['team'], 'description': m['description'],
                'runtime': runtime, 'model': self._model(), 'budget_usd_month': m['model']['budget_usd_month'],
                'replicas': sum(d['spec'].get('replicas', 1) for d in entry['rendered'] if d['kind'] == 'Deployment'), 'port': m['runtime']['port'], 'redaction': m['redaction'],
                'tools': [{'id': t['id'], 'access': t['access'], 'description': t['description']} for t in m['tools']],
                'data': 'none' if data == 'none' else {'database': data['database'], 'user_entry': data['user_entry'],
                                                        'row_level_security': data['row_level_security']},
                'reaches': sorted({f'{n}/{a}:{p}' for n, a, p in self._egress(entry) if n != 'ip'}),
                'manifest_source': entry['file'], 'live': self._live_block(name), 'health': self._health(name)}

    def _ops_live(self):
        """The ops agent's own live state: its API answered (traffic reaches only ready pods). It does not observe its own pod,
        so there is no digest or restart count for it."""
        snapshot = self._live('/v1/snapshot')
        if snapshot is None:
            return None
        return {'source': 'ops-agent /v1/snapshot', 'observed_at': round(self._clock(), 3), 'state': 'ANSWERING',
                'targets_watched': len(snapshot.get('findings') or {}), 'image_digests': []}

    def _ops_agent(self):
        from agent_platform.onboarding import PLATFORM_KEYS
        from agent_platform.ops.registry import ACTIONS
        o = self._opscfg
        container = o['deployment']['spec']['template']['spec']['containers'][0]
        targets = o['targets']
        tools = [{'id': 'observe', 'access': 'read', 'description': 'Watch %d registered workloads and %d onboarded agents, read-only.'
                  % (len(targets), len({key.split('.')[0] for key in o['observed']}))}]
        wording = {'restart': 'Restart a registered workload, once, after the owner approves.',
                   'scale': 'Scale a registered workload within its bounds, after the owner approves.'}
        tools += [{'id': a, 'access': 'approval', 'description': wording.get(a, a)} for a in ACTIONS]
        egress = self._egress(o)
        reaches = sorted({f'{n}/{a}:{p}' for n, a, p in egress if n != 'ip'})
        if any(n == 'ip' for n, _, _ in egress):
            reaches.append('kubernetes API (private control-plane range)')
        live = self._ops_live()
        return {'id': OPS, 'name': OPS, 'node': OPS, 'kind': 'platform', 'display': 'Security & Ops', 'namespace': 'ops', 'team': 'platform',
                'description': 'Watches the registered workloads and the onboarded agents read-only, diagnoses faults, and proposes '
                               'a restart or a bounded scale that runs only after the owner approves.',
                'runtime': self._runtime(container['command'][0]), 'model': self._model(), 'budget_usd_month': PLATFORM_KEYS['ops-explain'],
                'replicas': o['deployment']['spec'].get('replicas'), 'port': container['ports'][0]['containerPort'], 'redaction': 'required',
                'tools': tools, 'data': 'none', 'reaches': reaches,
                'targets': [{'target': k, 'min': t.min_replicas, 'max': t.max_replicas} for k, t in sorted(targets.items())],
                'manifest_source': o['file'], 'live': live,
                'health': {'state': 'running', 'source': 'ops-agent API answered (only ready pods receive traffic)'} if live else None}

    def agents(self):
        listed = [self._agent(n) for n in sorted(self._manifests)] + ([self._ops_agent()] if self._opscfg else [])
        return {'agents': sorted(listed, key=lambda a: a['name']), 'live_source': 'ops-agent /v1/snapshot',
                'live_available': self._live('/v1/snapshot') is not None}

    # onboarding ---------------------------------------------------------------------------------------------
    def _ops_onboarding(self):
        o, ns, file = self._opscfg, 'ops', self._opscfg['file']
        live = self._ops_live()
        posture = ((self._live('/v1/posture') or {}).get('network') or {}).get(ns)
        activity = self._live('/v1/activity')
        seen = [e for e in (activity or {}).get('events', []) if e.get('caller') == 'ops' and type(e.get('at')) in (int, float)
                and self._clock() - e['at'] <= REDACTION_RECENT_SECONDS]
        g = lambda gid, title, state, basis, source, detail: {'id': gid, 'title': title, 'state': state, 'basis': basis, 'source': source, 'detail': detail}
        out = [g('namespace', 'Its own namespace', 'verified', 'observed', 'ops-agent /v1/snapshot', 'its API answered at ops-agent.ops') if live else
               g('namespace', 'Its own namespace', 'declared', 'manifest', file, 'Deployment ops-agent in namespace ops')]
        if posture is None:
            out.append(g('network', 'Default-deny network', 'declared', 'manifest', 'platform/core/kubernetes/policies/network.yaml',
                         'default-deny rendered for ops; read-only API access and declared gateway/redactor/executor paths'))
        elif any(p['pods'] == 'all' and p['types'] == ['Egress', 'Ingress'] and not p['ingress'] and not p['egress'] for p in posture):
            out.append(g('network', 'Default-deny network', 'verified', 'observed', 'ops-agent /v1/posture', 'default-deny seen in the live NetworkPolicy list of ops'))
        else:
            out.append(g('network', 'Default-deny network', 'failing', 'observed', 'ops-agent /v1/posture', 'no default-deny policy in the live NetworkPolicy list of ops'))
        out.append(g('model_key', 'Scoped model key', 'declared', 'manifest', 'platform/core/src/agent_platform/onboarding.py',
                     'gateway key ops-explain, used only to explain a finding; the key is never readable here'))
        out.append(g('budget', 'Monthly budget', 'declared', 'manifest', 'platform/core/src/agent_platform/onboarding.py',
                     'ops-explain: %s per month' % self._ops_agent()['budget_usd_month']))
        out.append(g('redaction', 'Personal data redaction', 'verified', 'observed', 'redactor audit via ops-agent /v1/activity',
                     'a recent redactor event for the key of ops') if seen else
                   g('redaction', 'Personal data redaction', 'declared', 'manifest', 'platform/core/src/agent_platform/ops/explain.py',
                     'every explanation request is redacted before the model'))
        out.append(g('approval', 'Approval-gated actions', 'declared', 'manifest', 'platform/core/kubernetes/policies/admission.yaml',
                     'read-only Ops delegates %d registered targets to the separate approval-verifying executor; the admission policy '
                     'ops-agent-bounded-remediation limits every change' % len(o['targets'])))
        out.append(g('image', 'Signed image only', 'declared', 'manifest', 'platform/clouds/gke/images.json',
                     'image pinned by digest and signed by CI; the ops agent does not observe its own pod'))
        counts = {state: sum(x['state'] == state for x in out) for state in ('verified', 'declared', 'failing')}
        return {'agent': OPS, 'guarantees': out, 'counts': counts, 'verified': counts['verified'], 'total': len(out)}

    def onboarding(self, name):
        if name == OPS and self._opscfg:
            return self._ops_onboarding()
        if name not in self._manifests:
            return None
        entry, ns = self._manifests[name], 'agent-' + name
        m, file = entry['manifest'], entry['file']
        live, finding = self._live_block(name), self._finding(f'{ns}.agent')
        posture = ((self._live('/v1/posture') or {}).get('network') or {}).get(ns)  # None: not readable or ops down
        deny = lambda policies: any(p['pods'] == 'all' and p['types'] == ['Egress', 'Ingress'] and not p['ingress'] and not p['egress']
                                    for p in policies or [])
        reaches = sorted({a for n, a, _ in self._egress(entry) if n != 'ip'})
        declared = lambda gid, title, detail: {'id': gid, 'title': title, 'state': 'declared', 'basis': 'manifest',
                                               'source': file, 'detail': detail}
        verified = lambda gid, title, source, basis, detail: {'id': gid, 'title': title, 'state': 'verified', 'basis': basis,
                                                              'source': source, 'detail': detail}
        failing = lambda gid, title, source, detail: {'id': gid, 'title': title, 'state': 'failing', 'basis': 'observed',
                                                      'source': source, 'detail': detail}
        ns_doc = self._kind(entry['rendered'], 'Namespace')
        activity = self._live('/v1/activity')
        seen = [e for e in (activity or {}).get('events', []) if e.get('caller') == ns and type(e.get('at')) in (int, float)
                and self._clock() - e['at'] <= REDACTION_RECENT_SECONDS]
        out = []
        out.append(verified('namespace', 'Its own namespace', 'ops-agent /v1/snapshot', 'observed', 'a Deployment is running in ' + ns)
                   if live and finding['namespace'] == ns and ns_doc else
                   declared('namespace', 'Its own namespace', 'rendered Namespace ' + ns + ' (pod security restricted)'))
        if posture is None:
            out.append(declared('network', 'Default-deny network', 'default-deny policy rendered; egress only to ' + ', '.join(reaches)))
        elif deny(posture):
            out.append(verified('network', 'Default-deny network', 'ops-agent /v1/posture', 'observed',
                                'default-deny seen in the live NetworkPolicy list of ' + ns))
        else:
            out.append(failing('network', 'Default-deny network', 'ops-agent /v1/posture',
                               'no default-deny policy in the live NetworkPolicy list of ' + ns))
        out.append(declared('model_key', 'Scoped model key', 'gateway key agent-' + name + ' created by make up; the key is never readable here'))
        out.append(declared('budget', 'Monthly budget', 'budget_usd_month: %s' % m['model']['budget_usd_month']))
        out.append(verified('redaction', 'Personal data redaction', 'redactor audit via ops-agent /v1/activity', 'observed',
                            'a recent redactor event for the key of ' + ns) if seen else
                   declared('redaction', 'Personal data redaction', 'redaction: required; egress rendered to the redactor'
                            if 'redactor' in reaches else 'redaction: required'))
        out.append(declared('tools', 'Read-only tools', ', '.join(t['id'] for t in m['tools']) or 'no tools'))
        if live and live['pods_ready'] >= 1 and live['image_digests'] and live['pods_ready'] >= live['desired']:
            out.append(verified('image', 'Signed image only', 'ops-agent /v1/snapshot', 'inference',
                                'running pod => admitted under the enforced Binary Authorization policy (inferred: the policy itself is not read here)'))
        else:  # not ready (or not seen): the signature cannot be inferred; health is reported separately, never as a failure here
            out.append(declared('image', 'Signed image only', 'image pinned by digest and signed by CI; ' + (
                'no ready pod, so nothing can be inferred' if live else 'no running pod seen')))
        out.append(verified('ops', 'Ops monitoring', 'ops-agent /v1/snapshot', 'observed', 'a scan of ' + ns + '.agent is recent')
                   if live else declared('ops', 'Ops monitoring', 'registered read-only in the ops agent; no recent scan seen'))
        counts = {state: sum(g['state'] == state for g in out) for state in ('verified', 'declared', 'failing')}
        return {'agent': name, 'guarantees': out, 'counts': counts, 'verified': counts['verified'], 'total': len(out)}

    # topology -----------------------------------------------------------------------------------------------
    def topology(self):
        nodes, edges = [], []
        platform = {}
        for doc in self.facts['documents']:
            if doc.get('kind') in ('Deployment', 'StatefulSet'):
                platform[doc['metadata']['name']] = doc
        for name in sorted(self._manifests):
            m = self._manifests[name]['manifest']
            nodes.append({'id': 'agent-' + name, 'kind': 'agent', 'name': name, 'namespace': 'agent-' + name,
                          'data': 'none' if m['data'] == 'none' else m['data']['database']})
        for name in ('gateway-boundary', 'gateway', 'redactor', 'postgres', 'financial-frontdoor', 'ops-executor'):
            if name in platform:
                nodes.append({'id': name, 'kind': 'platform', 'name': name, 'namespace': platform[name]['metadata']['namespace']})
        if self._opscfg:
            nodes.append({'id': OPS, 'kind': 'agent', 'tenant': 'platform', 'name': OPS, 'namespace': 'ops', 'data': 'none'})
        nodes.append({'id': 'audit', 'kind': 'platform', 'name': 'audit', 'namespace': 'platform'})
        externals = {}
        for doc in self.facts['documents']:
            if doc.get('kind') != 'FQDNNetworkPolicy':
                continue
            pod = ((doc['spec'].get('podSelector') or {}).get('matchLabels') or {}).get('app.kubernetes.io/name')
            for rule in doc['spec'].get('egress') or []:
                for match in rule.get('matches') or []:
                    host = match.get('name')
                    if pod in platform and re.fullmatch(r'[a-z0-9.-]+\.googleapis\.com', str(host)):
                        externals[pod] = host
        labels = {'gateway': ('model-provider', 'model provider'), 'redactor': ('dlp', 'sensitive-data service')}
        for pod, host in sorted(externals.items()):
            ident, label = labels.get(pod, (pod + '-external', pod))
            nodes.append({'id': ident, 'kind': 'external', 'name': label, 'host': host})
            edges.append({'from': pod, 'to': ident, 'state': 'allowed', 'source': 'rendered FQDNNetworkPolicy'})
        nodes.append({'id': 'internet', 'kind': 'external', 'name': 'internet'})
        ip_egress = False
        for name in sorted(self._manifests):
            for ns, app, port in self._egress(self._manifests[name]):
                if ns == 'ip':
                    ip_egress = True
                elif app in platform and ns == platform[app]['metadata']['namespace']:
                    edges.append({'from': 'agent-' + name, 'to': app, 'port': port, 'state': 'allowed',
                                  'source': 'rendered NetworkPolicy agent-' + name + '/agent'})
        tenants = {'agent-' + n: (self._manifests[n], 'agent-' + n) for n in sorted(self._manifests)}
        if self._opscfg:
            tenants[OPS] = (self._opscfg, 'ops')
            for ns, app, port in self._egress(self._opscfg):
                if app in platform and ns == platform[app]['metadata']['namespace']:
                    edges.append({'from': OPS, 'to': app, 'port': port, 'state': 'allowed', 'source': 'rendered NetworkPolicy ops/ops-agent'})
        for policy in (d for d in self.facts['documents'] if d['kind'] == 'NetworkPolicy'):
            origin = policy.get('spec', {}).get('podSelector', {}).get('matchLabels', {}).get('app.kubernetes.io/name')
            if origin not in platform:
                continue
            for rule in policy['spec'].get('egress', []):
                for namespace, app, port in peer_names(rule):
                    if app in platform and namespace == platform[app]['metadata']['namespace']:
                        edges.append({'from': origin, 'to': app, 'port': port, 'state': 'allowed', 'source': 'declared RC1 NetworkPolicy'})
        reaches_ns = lambda entry: {ns for ns, _, _ in self._egress(entry)}
        denied = [{'from': a, 'to': b, 'why': 'default-deny; no rule allows it'}
                  for a in tenants for b in tenants if a != b and tenants[b][1] not in reaches_ns(tenants[a][0])]
        if not ip_egress:
            denied += [{'from': a, 'to': 'internet', 'why': 'default-deny; no egress rule to an address'} for a in tenants if a != OPS]
        if self._opscfg:
            blocks = [p for ns, p, _ in self._egress(self._opscfg) if ns == 'ip']
            if all(b == 'CONTROL_PLANE_CIDR' or (ipaddress.ip_network(b).is_private and ipaddress.ip_network(b).prefixlen == 28) for b in blocks):
                denied.append({'from': OPS, 'to': 'internet', 'why': 'default-deny; its only address rule is the private API-server range'})
        return {'nodes': nodes, 'edges': edges, 'denied': denied,
                'source': ('selected release manifest ' + (self.source_commit or '(source version unavailable)')
                           if self.facts['bound_to_release'] else 'current source render; not release-qualified'), 'live': False}

    # activity -----------------------------------------------------------------------------------------------
    def activity(self, limit=3):
        limit = max(1, min(int(limit), MAX_EVENTS))
        events, sources = [], {}
        redactor = self._live('/v1/activity')
        sources['redactor'] = 'ok' if redactor and redactor.get('available') else 'unavailable'
        events += [e for e in (redactor or {}).get('events', []) if e.get('kind') in ('masked', 'blocked')]
        snapshot = self._live('/v1/snapshot')
        sources['ops_timeline'] = 'ok' if snapshot else 'unavailable'
        for e in (snapshot or {}).get('timeline', []):
            kind = {'denied': 'blocked', 'approved': 'approved'}.get(e.get('stage'))
            if kind:
                events.append({'kind': kind, 'at': e.get('at'), 'source': 'ops-agent', 'target': e.get('target'), 'code': e.get('code')})
        for line in self._recent_audit():
            kind = {'ops_approval_signed': 'approved', 'ops_approval_refused': 'blocked'}.get(line.get('audit_event'))
            if kind:
                events.append({'kind': kind, 'at': line.get('at'), 'source': 'front-door audit', 'target': line.get('target'),
                               'code': line.get('reason'), 'action': line.get('action')})
        sources['front_door_audit'] = 'ok'
        events = [{k: v for k, v in e.items() if v is not None} for e in events if type(e.get('at')) in (int, float)]
        events.sort(key=lambda e: e['at'], reverse=True)
        return {'events': events[:limit], 'sources': sources}

    # attacks, example ---------------------------------------------------------------------------------------
    def attacks(self):
        """Only the mounted owner report. Missing or invalid current evidence cannot fall back to history."""
        from agent_platform import attack_results
        base = {'available': False, 'file': 'ConfigMap apps/attack-results', 'results': []}
        try:
            raw = self.live_attacks.read_text()
        except FileNotFoundError:
            return dict(base, status='missing')
        except OSError:
            return dict(base, status='unavailable')
        if len(raw.encode()) > 128_000:
            return dict(base, status='invalid')
        try:
            return attack_results.view(json.loads(raw), release_facts.evidence_binding(self.facts))
        except (ValueError, TypeError, KeyError):
            return dict(base, status='invalid')

    def example(self):
        path = self.examples_dir / 'rejected-agent/agent.yaml'
        try:
            text = path.read_text()
        except OSError:
            return {'available': False, 'file': 'docs/examples/rejected-agent/agent.yaml'}
        return {'available': True, 'file': 'docs/examples/rejected-agent/agent.yaml', 'text': text,
                'command': 'make onboard-check F=docs/examples/rejected-agent/agent.yaml'}

    # explain ------------------------------------------------------------------------------------------------
    def explain(self, topic):
        entry = EXPLAIN.get(topic)
        if entry is None:
            return None
        return dict(topic=topic, **entry['text'], proof=getattr(self, '_proof_' + topic.replace('-', '_'))(), file=entry['file'])

    def _network(self):
        posture = self._live('/v1/posture')
        network = (posture or {}).get('network')
        return posture, network if network else None

    def _proof_network(self):
        posture, network = self._network()
        if network is None:
            return None
        return {'source': 'ops-agent /v1/posture (live NetworkPolicy list)', 'observed_at': round(self._clock(), 3),
                'namespaces': network, 'unreadable': posture.get('unreadable', [])}

    def _proof_internet(self):
        posture, network = self._network()
        if network is None:
            return None
        blocks = [{'namespace': ns, 'policy': p['name'], 'cidr': peer[len('ipBlock:'):]}
                  for ns, policies in network.items() for p in policies for r in p['egress'] for peer in r['peers']
                  if peer.startswith('ipBlock:')]
        default_deny = {ns: any(p['pods'] == 'all' and p['types'] == ['Egress', 'Ingress'] and not p['egress'] and not p['ingress']
                                for p in policies) for ns, policies in network.items()}
        return {'source': 'ops-agent /v1/posture (live NetworkPolicy list)', 'observed_at': round(self._clock(), 3),
                'default_deny': default_deny, 'egress_to_addresses': blocks, 'unreadable': posture.get('unreadable', [])}

    def _proof_private_link(self):
        return None  # Private Service Connect is a cloud resource; no read-only source exists for it in the cluster

    def _service_proof(self, name):
        finding = self._finding('platform.' + name)
        if not self._fresh(finding):
            return None
        f = finding['facts']
        proof = {'source': 'ops-agent /v1/snapshot', 'observed_at': f['observed_at'], 'state': finding['finding'],
                 'pods_ready': f['pods_ready'], 'desired': finding['desired_replicas'], 'restarts': f['restarts'],
                 'image_digests': f['image_digests']}
        _, network = self._network()
        policies = [p for p in (network or {}).get('platform', []) if p['pods'] != 'all' and p['pods'].get('app.kubernetes.io/name') == name]
        if policies:
            proof['network_policies'] = policies
        return proof

    def _proof_redactor(self):
        proof = self._service_proof('redactor')
        activity = self._live('/v1/activity')
        if proof is not None and activity and activity.get('available'):
            proof['recent_masked'] = sum(e['kind'] == 'masked' for e in activity['events'])
            proof['recent_blocked'] = sum(e['kind'] == 'blocked' for e in activity['events'])
        return proof

    def _proof_gateway(self):
        return self._service_proof('gateway')

    def _proof_audit(self):
        for line in reversed(self._recent_audit()):
            if line.get('audit_event') != 'model_response_shape':
                scalars = {k: v for k, v in line.items() if type(v) in (str, int, float, bool)}
                return {'source': 'front-door audit stream (this process)', 'line': dict(list(scalars.items())[:10])}
        return None


EXPLAIN = {
    'network': {'file': 'platform/core/kubernetes/policies/network.yaml', 'text': {
        'title': 'Network wall',
        'plain': 'Agents cannot talk to each other. Each one reaches only the platform services it needs.',
        'how': 'The selected release declares namespace default-deny and explicit paths through trusted services. Live policy lists show configured rules, not a traffic test or complete drop log.',
        'without': "One compromised agent could read another agent's data or borrow its key."}},
    'private-link': {'file': 'platform/clouds/gke/kubernetes/gke.yaml', 'text': {
        'title': 'Private link',
        'plain': 'Calls to Google services use a private route, not the public internet.',
        'how': 'Egress is allowed only to the named Google API hostnames, resolved to private endpoints.',
        'without': 'Model and sensitive-data traffic would cross the public internet.'}},
    'internet': {'file': 'platform/core/kubernetes/policies/network.yaml', 'text': {
        'title': 'No way out',
        'plain': 'Agents cannot reach the internet.',
        'how': 'No egress rule points at an address range. The only exits are DNS and the platform services.',
        'without': 'A tricked agent could send data to any server.'}},
    'redactor': {'file': 'platform/core/src/agent_platform/programs/redactor_server.py', 'text': {
        'title': 'Redactor',
        'plain': 'Personal data is hidden from the model.',
        'how': 'Every model request goes through the redactor first. If it fails, the request is not sent.',
        'without': 'Names, emails and numbers would reach the model.'}},
    'gateway': {'file': 'platform/core/kubernetes/platform/workloads.yaml', 'text': {
        'title': 'Private model provider gateway',
        'plain': 'One key and one budget per agent.',
        'how': 'The trusted gateway frontend redacts accepted messages and forwards with private upstream credentials. Workers do not receive those keys.',
        'without': 'An agent could spend without limit or use another key.'}},
    'audit': {'file': 'platform/core/src/agent_platform/audit.py', 'text': {
        'title': 'Audit',
        'plain': 'Bounded component events support investigation.',
        'how': 'Trusted mediators emit their own events. Worker traces and stdout alone do not prove complete or authentic audit.',
        'without': 'Nothing could be shown or proven afterwards.'}},
}


for _topic, _title, _description, _source in (
    ('gateway-boundary', 'Mandatory redaction gateway', 'A trusted frontend redacts accepted messages before using private provider credentials.', 'platform/core/src/agent_platform/gateway_boundary.py'),
    ('financial-frontdoor', 'Trusted user and data boundary', 'Only this boundary holds user-authentication and database credentials; workers use active signed read capabilities.', 'platform/agents/financial/finance_agent/frontdoor.py'),
    ('ops-executor', 'Independent approval executor', 'Only this identity can patch registered workloads after verifying owner approval and consuming a durable one-use receipt.', 'platform/core/src/agent_platform/ops/executor.py'),
):
    EXPLAIN[_topic] = {'file': _source, 'text': {'title': _title, 'plain': _description,
                      'how': 'Declared RC1 source architecture; live deployment enforcement remains unverified.',
                      'without': 'A compromised worker could cross a boundary intended to be enforced independently.'}}


class Handler(web.Handler):
    """The existing front-door handler plus the console UI and the read-only console routes (same Host/Origin boundary)."""

    def send_header(self, key, value):
        if key == 'Content-Security-Policy':  # the console ships its own fonts (same origin); nothing else is widened
            value = value.replace("style-src 'self';", "style-src 'self'; font-src 'self';")
        super().send_header(key, value)

    def end_headers(self):
        commit = self.server.console.source_commit
        if commit:
            self.send_header('X-Platform-Source-Commit', commit)
        super().end_headers()

    def asset(self, path):
        """(bytes, content type) of one fixed UI file, or None. Only files that exist in the UI directory, by exact name."""
        name = 'index.html' if path == '/' else path[1:]
        kind = ASSET_TYPES.get(Path(name).suffix)
        parts = name.split('/')
        if kind is None or not (len(parts) == 1 or (len(parts) == 2 and parts[0] == 'typeface')) or not all(
                re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,80}', p) for p in parts):
            return None
        file = self.server.console.ui_dir.joinpath(*parts)
        return (file.read_bytes(), kind) if file.is_file() else None

    def do_GET(self):
        url = urlsplit(self.path)
        if not (url.path.startswith('/api/console/') or url.path in web.ASSETS or self.asset(url.path)):
            return super().do_GET()
        if not self.boundary():
            return
        if not url.path.startswith('/api/console/'):
            found = self.asset(url.path)  # the retired demo pages (web.ASSETS) are not served: only the console files are
            if found is None:
                self.respond(404, {'error': 'not_found'})
            else:
                self.respond(200, *found)
            return
        console, parts = self.server.console, url.path.split('/')[3:]
        try:
            if parts == ['topology']:
                result = console.topology()
            elif parts == ['agents']:
                result = console.agents()
            elif parts == ['attacks']:
                result = console.attacks()
            elif parts == ['example']:
                result = console.example()
            elif parts == ['activity']:
                limit = parse_qs(url.query).get('limit', ['3'])
                if len(limit) != 1 or not re.fullmatch(r'[0-9]{1,2}', limit[0]):
                    self.respond(400, {'error': 'invalid_limit'})
                    return
                result = console.activity(int(limit[0]))
            elif len(parts) == 2 and parts[0] == 'onboarding' and NAME.fullmatch(parts[1]):
                result = console.onboarding(parts[1])
            elif len(parts) == 2 and parts[0] == 'explain':
                result = console.explain(parts[1])
            else:
                result = None
        except Exception:
            self.respond(500, {'error': 'console_unavailable'})
            return
        if result is None:
            self.respond(404, {'error': 'not_found'})
        else:
            self.respond(200, result)


def attach(server, ops):
    """Serve the console UI and routes from an existing DemoServer."""
    server.console = Console(ops)
    server.RequestHandlerClass = Handler
