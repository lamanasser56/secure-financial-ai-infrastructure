"""Declared RBAC authority: one inventory generates manifests and checks observed bindings and privileges."""
from copy import deepcopy
import json
from pathlib import Path
import sys

DECLARATION = Path(__file__).with_name('authority.json')


def declaration():
    value = json.loads(DECLARATION.read_text())
    if value.get('version') != 1:
        raise ValueError('authority inventory version')
    return value


def agent_documents(namespace, workloads):
    value = declaration()
    role, binding = deepcopy(value['agent_role']), deepcopy(value['agent_binding'])
    for doc in (role, binding):
        doc['metadata']['namespace'] = namespace
    for rule in role['rules']:
        if rule.get('resourceNames') == '$workloads':
            rule['resourceNames'] = sorted(workloads)
    return [role, binding]


def inventory(workloads):
    """Registered namespaces/workload names select declarations; live RBAC never defines its own authority."""
    docs = [doc for doc in declaration()['core'] if doc['metadata']['namespace'] in workloads]
    core_namespaces = {doc['metadata']['namespace'] for doc in declaration()['core']}
    for ns, names in sorted(workloads.items()):
        if ns.startswith('agent-') and ns not in core_namespaces:
            docs.extend(agent_documents(ns, names))
    return {(d['kind'], d['metadata']['namespace'], d['metadata']['name']): d for d in docs
            if d['kind'] in ('Role', 'RoleBinding')}


def canonical_rules(rules):
    def normalize(value):
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items()}
        if isinstance(value, list):
            return sorted((normalize(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
        return value
    return normalize(rules)


def binding_matches(actual, declared):
    def subjects(items):
        result = []
        for item in items:
            # Kubernetes may omit the empty ServiceAccount apiGroup. No other subject field is ignored.
            subject = dict(item)
            if subject.get('kind') == 'ServiceAccount' and subject.get('apiGroup') == '':
                del subject['apiGroup']
            result.append(subject)
        return canonical_rules(result)
    return (actual.get('roleRef') == declared['roleRef']
            and subjects(actual.get('subjects') or []) == subjects(declared['subjects']))


def core_manifest():
    from agent_platform.onboarding import dump
    return '# GENERATED from agent_platform/ops/authority.json by python -m agent_platform.ops.authority. Do not edit.\n' + \
        '---\n' + dump(declaration()['core'])


def main():
    path = Path(__file__).resolve().parents[3] / 'kubernetes/policies/ops-agent-rbac.yaml'
    if sys.argv[1:] == ['--write']:
        path.write_text(core_manifest(), newline='\n')
    elif sys.argv[1:] == ['--check']:
        if path.read_text() != core_manifest():
            raise SystemExit('authority: generated core RBAC differs')
    else:
        raise SystemExit('usage: python -m agent_platform.ops.authority --write|--check')


if __name__ == '__main__':
    main()
