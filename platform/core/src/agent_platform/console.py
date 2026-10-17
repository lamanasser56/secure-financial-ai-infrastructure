"""Console data API (read-only, front door, loopback :8080): what the platform console screens show.

GET /api/console/topology           what exists and which paths are open or denied (rendered manifests shipped in the image)
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
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlsplit

import yaml

from agent_platform import audit
from runtime.agents import web

HERE = Path(__file__).resolve()
NAME = re.compile(r'[a-z][a-z0-9-]{1,20}[a-z0-9]')
GUARANTEES = ('namespace', 'network', 'model_key', 'budget', 'redaction', 'tools', 'image', 'ops')
FRESH_SECONDS = 120  # the ops agent scans every 15 s; a finding older than this is not "live"
MAX_EVENTS = 20
ASSET_TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
               '.woff2': 'font/woff2'}
REDACTION_RECENT_SECONDS = 3600  # how recent a redactor event for the agent's own key must be to count as seen


def locate():
    """(kubernetes dir, agent manifests dir, GKE overlay dir). The image keeps them side by side under /app/platform;
    the repository keeps them under platform/core, platform/agents and platform/clouds/gke."""
    image = HERE.parents[2]
    if (image / 'agents').is_dir():
        return image / 'kubernetes', image / 'agents', image / 'gke'
    platform = HERE.parents[3]
    return platform / 'core/kubernetes', platform / 'agents', platform / 'clouds/gke/kubernetes'


def locate_extras():
    """(UI dir, evidence dir, examples dir): side by side under /app/platform in the image; under platform/core/ui and docs/ in the repository."""
    image = HERE.parents[2]
    if (image / 'agents').is_dir():
        return image / 'ui', image / 'evidence', image / 'examples'
    return HERE.parents[2] / 'ui', HERE.parents[4] / 'docs/evidence', HERE.parents[4] / 'docs/examples'


def documents(path):
    if not path.is_file():
        return []
    return [d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict)]


def peer_names(rule):
    """Destination Services of one egress rule as [(namespace, app, port)], or ('ip', cidr) for an ipBlock."""
    found = []
    for peer in rule.get('to') or []:
        if 'ipBlock' in peer:
            found.append(('ip', peer['ipBlock'].get('cidr')))
            continue
        namespace = ((peer.get('namespaceSelector') or {}).get('matchLabels') or {}).get('kubernetes.io/metadata.name')
        app = ((peer.get('podSelector') or {}).get('matchLabels') or {}).get('app.kubernetes.io/name')
        for port in rule.get('ports') or [{}]:
            found.append((namespace, app, port.get('port')))
    return found


class Console:
    def __init__(self, ops, *, directories=None, extras=None, clock=time.time, recent_audit=audit.recent):
        """`ops(path)` GETs the ops agent's read-only API and returns the decoded JSON (raises when it is unreachable)."""
        self._ops, self._clock, self._recent_audit = ops, clock, recent_audit
        self.kube, self.agent_dir, self.gke = directories or locate()
        self.ui_dir, self.evidence_dir, self.examples_dir = extras or locate_extras()
        self._cache = {}
        self._manifests = self._load_manifests()

    # manifests ---------------------------------------------------------------------------------------------
    def _load_manifests(self):
        found = {}
        for path in sorted(self.agent_dir.glob('*/agent.yaml')):
            name = path.parent.name
            manifest = yaml.safe_load(path.read_text())
            rendered = documents(self.kube / 'agents' / (name + '.yaml'))
            if NAME.fullmatch(name) and isinstance(manifest, dict) and rendered:
                found[name] = {'manifest': manifest, 'rendered': rendered, 'file': f'platform/core/kubernetes/agents/{name}.yaml'}
        return found

    def _model(self):
        for doc in documents(self.kube / 'platform/generated/litellm.yaml'):
            for entry in doc.get('model_list') or []:
                return str((entry.get('litellm_params') or {}).get('model', '')).rpartition('/')[2] or None
        return None

    @staticmethod
    def _kind(rendered, kind, name=None):
        return next((d for d in rendered if d.get('kind') == kind and (name is None or d['metadata']['name'] == name)), None)

    def _egress(self, entry):
        policy = self._kind(entry['rendered'], 'NetworkPolicy', 'agent')
        found = []
        for rule in (policy or {}).get('spec', {}).get('egress') or []:
            found += peer_names(rule)
        return found

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
        finding = ((snapshot or {}).get('findings') or {}).get(target)
        if type(finding) is dict and type(finding.get('facts')) is dict:
            return finding
        return None

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
        command = (m['runtime']['command'] or [''])[0]
        version = re.search(r'python(3\.\d+)', command)
        runtime = 'node' if command.endswith('/node') else ('python ' + version.group(1) if version else None)
        data = m['data']
        return {'id': name, 'name': name, 'namespace': 'agent-' + name, 'team': m['team'], 'description': m['description'],
                'runtime': runtime, 'model': self._model(), 'budget_usd_month': m['model']['budget_usd_month'],
                'replicas': m['runtime']['replicas'], 'port': m['runtime']['port'], 'redaction': m['redaction'],
                'tools': [{'id': t['id'], 'access': t['access'], 'description': t['description']} for t in m['tools']],
                'data': 'none' if data == 'none' else {'database': data['database'], 'user_entry': data['user_entry'],
                                                        'row_level_security': data['row_level_security']},
                'reaches': sorted({f'{n}/{a}:{p}' for n, a, p in self._egress(entry) if n != 'ip'}),
                'manifest_source': entry['file'], 'live': self._live_block(name), 'health': self._health(name)}

    def agents(self):
        return {'agents': [self._agent(n) for n in sorted(self._manifests)], 'live_source': 'ops-agent /v1/snapshot',
                'live_available': self._live('/v1/snapshot') is not None}

    # onboarding ---------------------------------------------------------------------------------------------
    def onboarding(self, name):
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
        for doc in documents(self.kube / 'platform/workloads.yaml'):
            if doc.get('kind') in ('Deployment', 'StatefulSet'):
                platform[doc['metadata']['name']] = doc
        for name in sorted(self._manifests):
            m = self._manifests[name]['manifest']
            nodes.append({'id': 'agent-' + name, 'kind': 'agent', 'name': name, 'namespace': 'agent-' + name,
                          'data': 'none' if m['data'] == 'none' else m['data']['database']})
        for name in ('gateway', 'redactor', 'postgres'):
            if name in platform:
                nodes.append({'id': name, 'kind': 'platform', 'name': name, 'namespace': 'platform'})
        nodes.append({'id': 'audit', 'kind': 'platform', 'name': 'audit', 'namespace': 'platform'})
        externals = {}
        for path in (self.gke / 'generated/provider-egress.yaml', self.gke / 'gke.yaml'):
            for doc in documents(path):
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
                elif ns == 'platform' and app in platform:
                    edges.append({'from': 'agent-' + name, 'to': app, 'port': port, 'state': 'allowed',
                                  'source': 'rendered NetworkPolicy agent-' + name + '/agent'})
        agents = sorted(self._manifests)
        denied = [{'from': 'agent-' + a, 'to': 'agent-' + b, 'why': 'default-deny; no rule allows it'}
                  for a in agents for b in agents if a != b and not any(
                      ns == 'agent-' + b for ns, _, _ in self._egress(self._manifests[a]))]
        if not ip_egress:
            denied += [{'from': 'agent-' + a, 'to': 'internet', 'why': 'default-deny; no egress rule to an address'} for a in agents]
        return {'nodes': nodes, 'edges': edges, 'denied': denied,
                'source': 'rendered manifests shipped in the image', 'live': False}

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
    ATTACK_CASE = re.compile(r'[a-z][a-z0-9_]{2,80}')

    def attacks(self):
        """Latest attack-suite results from the committed results file: case, result, time only. Not a live run."""
        path = self.evidence_dir / 'attack-suite.json'
        try:
            data = json.loads(path.read_text())
            rows = [{'case': r['case'], 'result': r['result'], 'at': r['at']} for r in data['results']
                    if r['case'] != 'financial_setup']  # setup is a precondition, not an attack
            if not all(self.ATTACK_CASE.fullmatch(r['case']) and r['result'] in ('PASS', 'FAIL') and type(r['at']) is str
                       and len(r['at']) <= 40 for r in rows) or type(data['completed_at']) is not str:
                raise ValueError('shape')
        except (OSError, ValueError, KeyError, TypeError):
            return {'available': False, 'file': 'docs/evidence/attack-suite.json', 'results': []}
        return {'available': True, 'file': 'docs/evidence/attack-suite.json', 'completed_at': data['completed_at'][:40],
                'results': rows, 'stopped': sum(r['result'] == 'PASS' for r in rows), 'total': len(rows)}

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
        'how': 'Every namespace is default-deny. Only DNS, the gateway and the redactor are allowed. Every drop is logged.',
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
        'title': 'Model gateway',
        'plain': 'One key and one budget per agent.',
        'how': 'Agents call the gateway with their own scoped key. Only the gateway talks to the model provider.',
        'without': 'An agent could spend without limit or use another key.'}},
    'audit': {'file': 'platform/core/src/agent_platform/audit.py', 'text': {
        'title': 'Audit',
        'plain': 'Every request is recorded.',
        'how': 'Each component prints one JSON line with bounded fields and no content. The log pipeline stores them.',
        'without': 'Nothing could be shown or proven afterwards.'}},
}


class Handler(web.Handler):
    """The existing front-door handler plus the console UI and the read-only console routes (same Host/Origin boundary)."""

    def send_header(self, key, value):
        if key == 'Content-Security-Policy':  # the console ships its own fonts (same origin); nothing else is widened
            value = value.replace("style-src 'self';", "style-src 'self'; font-src 'self';")
        super().send_header(key, value)

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
