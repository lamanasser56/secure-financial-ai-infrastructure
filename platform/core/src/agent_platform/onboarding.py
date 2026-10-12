"""Agent onboarding: platform/agents/<name>/agent.yaml -> validated -> Kubernetes objects the agent inherits.

`make onboard A=<name>` calls `python -m agent_platform.onboarding render <name>`. A team writes only the manifest;
the platform decides everything security-relevant (docs/agent-developer-guide.md):

- its own namespace `agent-<name>`: Pod Security "restricted", default-deny NetworkPolicies, a quota with no load
  balancers or node ports, no Kubernetes API token, a hardened container;
- egress only to DNS, the redactor and the LiteLLM gateway (never the internet, never a model provider);
- a scoped gateway key with the declared monthly budget (the platform total stays $10) and a redactor client key,
  created by `make up` (platform_secrets.onboard) without rotating any existing key;
- tools only from the registry, read-only, enabled.

Anything outside the closed manifest shape is rejected with a reason, before anything is rendered.
`check` verifies that the committed generated files match the manifests (run by `make test`).
"""
import json
from pathlib import Path
import re
import sys

import yaml

REPO = Path(__file__).resolve().parents[4]
AGENTS = REPO / 'platform/agents'
GENERATED = REPO / 'platform/core/kubernetes/agents'
IMAGES = REPO / 'platform/clouds/gke/images.json'
REGISTRY = REPO / 'contracts/agents/tool-registry.json'

PLATFORM_TOTAL_USD = 10.0
# Platform-owned gateway keys (not onboarded agents): the infrastructure demo profile and ops explanations.
PLATFORM_KEYS = {'app-infrastructure': 2.5, 'ops-explain': 2.0}
# Images that are platform components; an agent may only run an agent image that CI signed and pinned.
PLATFORM_IMAGES = {'gateway', 'database', 'redactor', 'ops-agent'}
RESERVED = {'platform', 'apps', 'ops', 'default', 'app', 'gateway', 'redactor', 'postgres', 'schema', 'ops-agent',
            'infrastructure', 'kube-system', 'kube-public', 'kube-node-lease'}
# Agents that still run inside the front door (apps/app) until the Financial Agent rewrite moves them out.
FRONT_DOOR = {'financial'}
DATA_ROLES = {'portfolio_app'}
GATEWAY = ('platform', 'gateway', 4000)
REDACTOR = ('platform', 'redactor', 4003)
NAME = re.compile(r'[a-z][a-z0-9-]{1,20}[a-z0-9]')


class Rejected(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def closed(value, allowed, where, required=None):
    require(isinstance(value, dict), where + ': must be a mapping')
    unknown = sorted(set(value) - set(allowed))
    require(not unknown, where + ': not allowed: ' + ', '.join(unknown))
    missing = sorted(set(required if required is not None else allowed) - set(value))
    require(not missing, where + ': missing: ' + ', '.join(missing))


def quantity(value, unit, maximum, where):
    match = re.fullmatch(r'([1-9][0-9]{0,3})' + unit, str(value))
    require(match is not None and int(match.group(1)) <= maximum, where + ': must be at most %d%s' % (maximum, unit))


def tools_registry():
    return {t['id']: t for t in json.loads(REGISTRY.read_text())['tools']}


def names():
    return sorted(p.name for p in AGENTS.iterdir() if (p / 'agent.yaml').is_file())


def load(name, *, others=None):
    require(NAME.fullmatch(name or '') is not None and name not in RESERVED, 'agent name: lowercase, 3-22 characters, not reserved')
    path = AGENTS / name / 'agent.yaml'
    require(path.is_file(), 'no manifest: platform/agents/' + name + '/agent.yaml')
    manifest = yaml.safe_load(path.read_text())
    validate(manifest, name, others=others)
    return manifest


def validate(m, name, *, others=None):
    """Closed shape + platform rules. `others` are the other manifests (for the shared budget)."""
    closed(m, {'agent', 'team', 'description', 'placement', 'runtime', 'model', 'redaction', 'tools', 'data'}, 'manifest',
           {'agent', 'team', 'description', 'placement', 'model', 'redaction', 'tools', 'data'})
    require(m['agent'] == name, 'agent must match its directory name')
    for field, limit in (('team', 60), ('description', 200)):
        require(isinstance(m[field], str) and 0 < len(m[field].strip()) <= limit, field + ': 1-%d characters' % limit)
    require(m['placement'] in ('namespace', 'front-door'), 'placement: namespace (front-door is legacy)')
    require(m['placement'] == 'namespace' or name in FRONT_DOOR, 'placement front-door is reserved for the legacy Financial Agent')
    require(m['redaction'] == 'required', 'redaction: must be required (every model call is redacted first)')
    # Model: a budget only. The alias, provider, model version and credentials belong to the platform.
    closed(m['model'], {'budget_usd_month'}, 'model')
    budget = m['model']['budget_usd_month']
    require(type(budget) is float and 0 < budget <= 5.0 and round(budget, 2) == budget,
            'model.budget_usd_month: a number of dollars above 0 and at most 5.00')
    total = sum(PLATFORM_KEYS.values()) + budget + sum(o['model']['budget_usd_month'] for o in (others or []))
    require(round(total, 2) <= PLATFORM_TOTAL_USD, 'model budget: the platform total would exceed $10.00/month')
    # Tools: registered, enabled, read-only. Nothing that writes can be onboarded.
    registry = tools_registry()
    require(isinstance(m['tools'], list) and len(m['tools']) == len(set(m['tools'])) <= 5, 'tools: a list of up to 5 distinct ids')
    for tool in m['tools']:
        require(tool in registry, 'tool not registered: ' + str(tool))
        entry = registry[tool]
        require(entry['enabled'] is True, 'tool disabled: ' + tool)
        require(entry['operation_type'] == 'read' and entry['risk_classification'].endswith('_read'), 'tool is not read-only: ' + tool)
        require(entry['approval']['required'] is False, 'tool needs approval (not onboardable): ' + tool)
    # Data: none, or read access through an existing non-owner role under row-level security.
    if m['data'] != 'none':
        closed(m['data'], {'role', 'access', 'row_level_security'}, 'data')
        require(m['data']['role'] in DATA_ROLES, 'data.role: must be an existing platform role')
        require(m['data']['access'] == 'read', 'data.access: read only')
        require(m['data']['row_level_security'] == 'required', 'data.row_level_security: required')
    if m['placement'] == 'front-door':
        require('runtime' not in m, 'runtime: not allowed for front-door placement')
        return
    require('runtime' in m, 'runtime: required for namespace placement')
    r = m['runtime']
    closed(r, {'image', 'command', 'port', 'replicas', 'resources'}, 'runtime')
    images = json.loads(IMAGES.read_text())['images']
    require(r['image'] in images and r['image'] not in PLATFORM_IMAGES,
            'runtime.image: must be an agent image signed and pinned by CI (platform/clouds/gke/images.json)')
    require(isinstance(r['command'], list) and 1 <= len(r['command']) <= 8
            and all(isinstance(c, str) and 0 < len(c) <= 120 and '\n' not in c for c in r['command']), 'runtime.command: 1-8 short strings')
    require(type(r['port']) is int and 1024 <= r['port'] <= 65535, 'runtime.port: 1024-65535 (no privileged ports)')
    require(type(r['replicas']) is int and 1 <= r['replicas'] <= 2, 'runtime.replicas: 1 or 2')
    closed(r['resources'], {'cpu', 'memory'}, 'runtime.resources')
    quantity(r['resources']['cpu'], 'm', 250, 'runtime.resources.cpu')
    quantity(r['resources']['memory'], 'Mi', 256, 'runtime.resources.memory')


def load_all():
    found = names()
    manifests = {}
    for name in found:
        path = AGENTS / name / 'agent.yaml'
        manifests[name] = yaml.safe_load(path.read_text())
    for name in found:  # each validated against the budget of all the others
        validate(manifests[name], name, others=[m for n, m in manifests.items() if n != name])
    return manifests


def key_alias(manifest):
    return ('app-' if manifest['placement'] == 'front-door' else 'agent-') + manifest['agent']


def budgets(manifests):
    """Every gateway virtual key and its monthly budget (platform keys + onboarded agents)."""
    return dict(PLATFORM_KEYS, **{key_alias(m): m['model']['budget_usd_month'] for m in manifests.values()})


def namespace_agents(manifests):
    return sorted(n for n, m in manifests.items() if m['placement'] == 'namespace')


def _peer(namespace, name, port):
    return {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': namespace}},
                    'podSelector': {'matchLabels': {'app.kubernetes.io/name': name}}}],
            'ports': [{'protocol': 'TCP', 'port': port}]}


def render_agent(m):
    name, r = m['agent'], m['runtime']
    ns = 'agent-' + name
    labels = {'app.kubernetes.io/name': 'agent', 'app.kubernetes.io/part-of': 'agent-platform', 'agent-platform/agent': name}
    meta = lambda kind_name: {'name': kind_name, 'namespace': ns}
    cpu, memory = r['resources']['cpu'], r['resources']['memory']
    return [
        {'apiVersion': 'v1', 'kind': 'Namespace',
         'metadata': {'name': ns, 'labels': {'agent-platform/tier': 'agent', 'agent-platform/agent': name,
                                             'pod-security.kubernetes.io/enforce': 'restricted',
                                             'pod-security.kubernetes.io/enforce-version': 'latest',
                                             'pod-security.kubernetes.io/audit': 'restricted',
                                             'pod-security.kubernetes.io/warn': 'restricted'}}},
        {'apiVersion': 'v1', 'kind': 'ResourceQuota', 'metadata': meta('bounds'),
         'spec': {'hard': {'pods': str(r['replicas'] + 1), 'requests.cpu': '250m', 'requests.memory': '256Mi',
                           'limits.cpu': '500m', 'limits.memory': '512Mi', 'persistentvolumeclaims': '0',
                           'services.loadbalancers': '0', 'services.nodeports': '0'}}},
        {'apiVersion': 'v1', 'kind': 'LimitRange', 'metadata': meta('defaults'),
         'spec': {'limits': [{'type': 'Container', 'default': {'cpu': cpu, 'memory': memory},
                              'defaultRequest': {'cpu': cpu, 'memory': memory}, 'max': {'cpu': '250m', 'memory': '256Mi'}}]}},
        {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': meta('agent'), 'automountServiceAccountToken': False},
        {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': dict(meta('agent'), labels=labels),
         'spec': {'replicas': r['replicas'], 'revisionHistoryLimit': 3,
                  'selector': {'matchLabels': {'app.kubernetes.io/name': 'agent'}},
                  'template': {'metadata': {'labels': labels},
                               'spec': {'serviceAccountName': 'agent', 'automountServiceAccountToken': False,
                                        'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532,
                                                            'fsGroup': 65532,  # the 0400 key file is readable by the agent
                                                            'seccompProfile': {'type': 'RuntimeDefault'}},
                                        'containers': [{
                                            'name': 'agent', 'image': 'agent-platform/' + r['image'], 'command': r['command'],
                                            'env': [{'name': 'PYTHONPATH', 'value': '/app/platform/src:/app'},
                                                    {'name': 'AGENT_NAME', 'value': name},
                                                    {'name': 'AGENT_PORT', 'value': str(r['port'])}],
                                            'ports': [{'name': 'http', 'containerPort': r['port']}],
                                            'readinessProbe': {'httpGet': {'path': '/healthz', 'port': r['port']}, 'periodSeconds': 10},
                                            'resources': {'requests': {'cpu': cpu, 'memory': memory},
                                                          'limits': {'cpu': cpu, 'memory': memory}},
                                            'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                                                                'capabilities': {'drop': ['ALL']},
                                                                'seccompProfile': {'type': 'RuntimeDefault'}},
                                            'volumeMounts': [{'name': 'keys', 'mountPath': '/secrets/agent', 'readOnly': True}]}],
                                        'volumes': [{'name': 'keys', 'secret': {'secretName': 'agent', 'defaultMode': 0o400}}]}}}},
        {'apiVersion': 'v1', 'kind': 'Service', 'metadata': meta('agent'),
         'spec': {'type': 'ClusterIP', 'selector': {'app.kubernetes.io/name': 'agent'},
                  'ports': [{'name': 'http', 'port': r['port'], 'targetPort': r['port']}]}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': meta('default-deny'),
         'spec': {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress']}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': meta('allow-dns'),
         'spec': {'podSelector': {}, 'policyTypes': ['Egress'],
                  'egress': [{'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                                      'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
                              'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]}]}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': meta('agent'),
         'spec': {'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'agent'}}, 'policyTypes': ['Egress'],
                  'egress': [_peer(*GATEWAY), _peer(*REDACTOR)]}},
    ]


def render_platform_access(manifests):
    """Additive NetworkPolicies in `platform`: the gateway and the redactor accept each onboarded agent namespace."""
    docs = []
    for name in namespace_agents(manifests):
        for target, port in (('gateway', GATEWAY[2]), ('redactor', REDACTOR[2])):
            docs.append({'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
                         'metadata': {'name': 'agent-' + name + '-to-' + target, 'namespace': 'platform'},
                         'spec': {'podSelector': {'matchLabels': {'app.kubernetes.io/name': target}}, 'policyTypes': ['Ingress'],
                                  'ingress': [{'from': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'agent-' + name}},
                                                         'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'agent'}}}],
                                               'ports': [{'protocol': 'TCP', 'port': port}]}]}})
    return docs


HEADER = '# GENERATED by `make onboard` from platform/agents/*/agent.yaml. Do not edit.\n'


class _IndentedDumper(yaml.SafeDumper):
    """Indented sequences, as the repository's yamllint configuration requires."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def dump(docs):
    return '---\n'.join(yaml.dump(d, Dumper=_IndentedDumper, sort_keys=True, default_flow_style=False) for d in docs)


def outputs():
    manifests = load_all()
    files = {}
    for name in namespace_agents(manifests):
        files[GENERATED / (name + '.yaml')] = render_agent(manifests[name])
    files[GENERATED / 'platform-access.yaml'] = render_platform_access(manifests)
    text = {path: HEADER + '---\n' + dump(docs) for path, docs in files.items()}
    resources = sorted(p.name for p in text)
    text[GENERATED / 'kustomization.yaml'] = HEADER + dump(
        [{'apiVersion': 'kustomize.config.k8s.io/v1beta1', 'kind': 'Kustomization', 'resources': resources}])
    return manifests, text


def summary(manifest):
    inherited = ['redaction before every model call', 'gateway key only (no provider access)', 'audit']
    if manifest['placement'] == 'namespace':
        inherited = ['own namespace agent-' + manifest['agent'] + ' (Pod Security restricted)',
                     'default-deny network; egress only to the redactor and the gateway',
                     'no Kubernetes API token', 'no public Service'] + inherited
    return {'agent': manifest['agent'], 'result': 'ACCEPTED', 'placement': manifest['placement'],
            'gateway_key': key_alias(manifest), 'monthly_budget_usd': manifest['model']['budget_usd_month'],
            'tools': manifest['tools'], 'inherits': inherited}


def main(argv):
    if len(argv) not in (1, 2) or argv[0] not in ('render', 'check') or (argv[0] == 'render' and len(argv) != 2):
        raise SystemExit('usage: onboarding render <agent> | onboarding check')
    try:
        if argv[0] == 'render':
            load(argv[1], others=[m for n, m in load_all_unchecked().items() if n != argv[1]])
        manifests, text = outputs()
    except Rejected as rejected:
        print(json.dumps({'result': 'REJECTED', 'reason': str(rejected)}))
        raise SystemExit(2)
    if argv[0] == 'check':
        drift = [str(p.relative_to(REPO)) for p, t in text.items() if not p.exists() or p.read_text() != t]
        stale = [str(p.relative_to(REPO)) for p in GENERATED.glob('*.yaml') if p not in text]
        print(json.dumps({'agents': sorted(manifests), 'drift': drift, 'stale': stale}))
        raise SystemExit(1 if drift or stale else 0)
    GENERATED.mkdir(parents=True, exist_ok=True)
    for path in GENERATED.glob('*.yaml'):
        if path not in text:
            path.unlink()
    for path, value in text.items():
        path.write_text(value)
    print(json.dumps(summary(manifests[argv[1]]), indent=1))


def load_all_unchecked():
    return {n: yaml.safe_load((AGENTS / n / 'agent.yaml').read_text()) for n in names()}


if __name__ == '__main__':
    main(sys.argv[1:])
