"""Protective posture checks over the registered namespaces (read-only).

Findings: NO_NETWORK_POLICY (no default-deny), RUNS_AS_ROOT / PRIVILEGED, UNEXPECTED_ROLE_BINDING (any binding
outside the declared authority inventory), IMAGE_REJECTED (admission/Binary Authorization denial events).
"""
from agent_platform.k8s import KubeError
from agent_platform.ops import authority


def _peer(peer):
    if 'ipBlock' in peer:
        return 'ipBlock:' + str((peer['ipBlock'] or {}).get('cidr', '?'))
    labels = lambda selector: ','.join(f'{k}={v}' for k, v in sorted(((selector or {}).get('matchLabels') or {}).items()))
    return (labels(peer.get('namespaceSelector')) or '*') + '/' + (labels(peer.get('podSelector')) or '*')


def summarize(policy):
    """One NetworkPolicy reduced to its shape (names, selectors, ports); no annotations or other metadata."""
    spec = policy['spec']
    rule = lambda r, side: {'peers': [_peer(p) for p in r.get(side) or []],
                            'ports': [f"{p.get('protocol', 'TCP')}/{p.get('port')}" for p in r.get('ports') or []]}
    return {'name': policy['metadata']['name'], 'pods': (spec.get('podSelector') or {}).get('matchLabels') or 'all',
            'types': sorted(spec.get('policyTypes') or []),
            'ingress': [rule(r, 'from') for r in spec.get('ingress') or []],
            'egress': [rule(r, 'to') for r in spec.get('egress') or []]}


def check(client, namespaces, workloads):
    findings, network, unreadable = [], {}, []
    expected = authority.inventory(workloads)
    for ns in namespaces:
        try:  # read on its own: a namespace whose other lists are not readable can still prove its network policies
            policies = client.list('networkpolicies', ns)
            network[ns] = [summarize(p) for p in policies]
        except KubeError as error:
            policies = None
            unreadable.append(ns)
            findings.append({'namespace': ns, 'finding': 'UNREADABLE', 'detail': str(error.status)})
        try:
            pods = client.list('pods', ns)
            bindings = client.list('rolebindings', ns)
            roles = client.list('roles', ns)
            events = client.list('events', ns)
        except KubeError as error:
            if policies is not None:  # (a namespace already reported unreadable above is not reported twice)
                findings.append({'namespace': ns, 'finding': 'UNREADABLE', 'detail': str(error.status)})
            continue
        if policies is not None and not any(
                p['spec'].get('podSelector') == {} and set(p['spec'].get('policyTypes', [])) == {'Ingress', 'Egress'}
                and not p['spec'].get('ingress') and not p['spec'].get('egress') for p in policies):
            findings.append({'namespace': ns, 'finding': 'NO_NETWORK_POLICY'})
        for pod in pods:
            spec = pod.get('spec') or {}
            pod_ctx = spec.get('securityContext') or {}
            for c in spec.get('containers', []):
                ctx = c.get('securityContext') or {}
                if ctx.get('privileged'):
                    findings.append({'namespace': ns, 'finding': 'PRIVILEGED', 'pod': pod['metadata']['name']})
                run_as = ctx.get('runAsUser', pod_ctx.get('runAsUser'))
                if run_as == 0 or not (ctx.get('runAsNonRoot', pod_ctx.get('runAsNonRoot'))):
                    findings.append({'namespace': ns, 'finding': 'RUNS_AS_ROOT', 'pod': pod['metadata']['name']})
        for binding in bindings:
            declared = expected.get(('RoleBinding', ns, binding['metadata']['name']))
            if declared is None or not authority.binding_matches(binding, declared):
                findings.append({'namespace': ns, 'finding': 'UNEXPECTED_ROLE_BINDING', 'binding': binding['metadata']['name']})
        for role in roles:
            declared = expected.get(('Role', ns, role['metadata']['name']))
            if declared is None or authority.canonical_rules(role.get('rules', [])) != authority.canonical_rules(declared['rules']):
                findings.append({'namespace': ns, 'finding': 'UNEXPECTED_ROLE', 'role': role['metadata']['name']})
        seen = {('RoleBinding', ns, b['metadata']['name']) for b in bindings} | {('Role', ns, r['metadata']['name']) for r in roles}
        for kind, namespace, name in sorted(expected.keys() - seen):
            if namespace == ns:
                findings.append({'namespace': ns, 'finding': 'MISSING_ROLE_BINDING' if kind == 'RoleBinding' else 'MISSING_ROLE',
                                 'binding' if kind == 'RoleBinding' else 'role': name})
        for event in events:
            message = str(event.get('message', '')).lower()
            if event.get('reason') == 'FailedCreate' and ('image policy' in message or 'binary authorization' in message):
                findings.append({'namespace': ns, 'finding': 'IMAGE_REJECTED',
                                 'object': (event.get('involvedObject') or {}).get('name')})
    return {'findings': findings, 'namespaces': list(namespaces), 'clean': not findings, 'network': network,
            'unreadable': sorted(unreadable)}
