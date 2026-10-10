#!/usr/bin/env python3
"""Render the GKE overlay into one manifest and refuse it unless every platform invariant holds.

Inputs (contract with platform/clouds/gke/terraform outputs): project ID, control-plane CIDR, gateway and
redactor service-account emails, and images.json (signed digests). The same invariant checks run offline in
`make test` and before every `make up`.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

HERE = Path(__file__).resolve().parent
OVERLAY = HERE / 'kubernetes'
NAMESPACES = ('platform', 'apps', 'ops')
IMAGE_NAMES = ('gateway', 'database', 'redactor', 'app', 'ops-agent')
WORKLOAD_IDENTITY = {('platform', 'gateway'), ('platform', 'redactor')}
FORBIDDEN_KINDS = {'Ingress', 'Gateway', 'HTTPRoute', 'ClusterRole', 'ClusterRoleBinding', 'PodSecurityPolicy',
                   'MutatingWebhookConfiguration', 'ValidatingWebhookConfiguration'}
POD_KINDS = {'Deployment': ('spec', 'template', 'spec'), 'StatefulSet': ('spec', 'template', 'spec'),
             'Job': ('spec', 'template', 'spec'), 'Pod': ('spec',)}


class Rejected(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Rejected(message)


def kustomize(kubectl='kubectl'):
    result = subprocess.run([kubectl, 'kustomize', '--load-restrictor', 'LoadRestrictionsNone', str(OVERLAY)],
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0, 'kustomize failed: ' + result.stderr.strip()[:300])
    return result.stdout


def substitute(text, *, project_id, control_plane_cidr, gateway_gsa, redactor_gsa, images, allow_pending=False):
    require(re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', project_id or ''), 'project id')
    network = ipaddress.ip_network(control_plane_cidr)
    require(network.is_private and network.prefixlen == 28, 'control plane cidr')
    for email in (gateway_gsa, redactor_gsa):
        require(re.fullmatch(r'[a-z][a-z0-9-]{4,29}@' + re.escape(project_id) + r'\.iam\.gserviceaccount\.com', email or ''), 'service account')
    registry = images['registry'].replace('PROJECT_ID', project_id)
    require(re.fullmatch(r'us-east1-docker\.pkg\.dev/[a-z0-9-]+/[a-z0-9-]+/', registry), 'registry')
    refs = {}
    for name in IMAGE_NAMES:
        ref = images['images'][name]
        if ref == 'PENDING_CI' and allow_pending:
            ref = 'pending-' + name + '@sha256:' + '0' * 64
        require(re.fullmatch(r'[a-z0-9-]+@sha256:[a-f0-9]{64}', ref), 'image not digest-pinned: ' + name)
        refs[name] = registry + ref
    for name, ref in refs.items():
        text = re.sub(r'(image: )agent-platform/' + re.escape(name) + r'\b(?![-\w])', r'\g<1>' + ref, text)
        text = text.replace('IMAGE:' + name, ref)
    for placeholder, value in (('GATEWAY_GSA', gateway_gsa), ('REDACTOR_GSA', redactor_gsa),
                               ('CONTROL_PLANE_CIDR', str(network)), ('PROJECT_ID', project_id)):
        text = text.replace(placeholder, value)
    return text, refs


def dig(item, path):
    for key in path:
        item = item.get(key) if isinstance(item, dict) else None
    return item


def validate(docs, refs):
    """Platform invariants on the final manifest. Returns a summary; raises Rejected on any violation."""
    allowed_images = set(refs.values())
    by_kind = {}
    for doc in docs:
        by_kind.setdefault(doc['kind'], []).append(doc)
        require(doc['kind'] not in FORBIDDEN_KINDS, 'forbidden kind: ' + doc['kind'])
        raw = json.dumps(doc)
        for token in ('PROJECT_ID', 'CONTROL_PLANE_CIDR', 'GATEWAY_GSA', 'REDACTOR_GSA', 'IMAGE:'):
            require(token not in raw, 'unrendered placeholder ' + token + ' in ' + doc['kind'] + '/' + doc['metadata']['name'])
    namespaces = {d['metadata']['name']: d for d in by_kind.get('Namespace', [])}
    require(set(namespaces) == set(NAMESPACES), 'namespaces')
    for name, ns in namespaces.items():
        require(ns['metadata']['labels'].get('pod-security.kubernetes.io/enforce') == 'restricted', 'PSS restricted: ' + name)
        deny = [p for p in by_kind['NetworkPolicy'] if p['metadata']['namespace'] == name and p['metadata']['name'] == 'default-deny']
        require(len(deny) == 1 and deny[0]['spec'] == {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress']}, 'default deny: ' + name)
    for svc in by_kind.get('Service', []):
        require(svc['spec'].get('type', 'ClusterIP') == 'ClusterIP' and 'externalIPs' not in svc['spec'], 'only ClusterIP Services')
    for sa in by_kind.get('ServiceAccount', []):
        key = (sa['metadata']['namespace'], sa['metadata']['name'])
        require(sa.get('automountServiceAccountToken') is False, 'automount off: ' + str(key))
        has_wi = 'iam.gke.io/gcp-service-account' in (sa['metadata'].get('annotations') or {})
        require(has_wi == (key in WORKLOAD_IDENTITY), 'workload identity only for gateway/redactor: ' + str(key))
    images_used = set()
    for kind, path in POD_KINDS.items():
        for doc in by_kind.get(kind, []):
            where = kind + '/' + doc['metadata']['name']
            pod = dig(doc, path)
            ctx = pod.get('securityContext') or {}
            require(ctx.get('runAsNonRoot') is True and ctx.get('seccompProfile') == {'type': 'RuntimeDefault'}, 'pod security: ' + where)
            require(pod.get('automountServiceAccountToken') is False, 'pod token automount: ' + where)
            for flag in ('hostNetwork', 'hostPID', 'hostIPC'):
                require(not pod.get(flag), flag + ': ' + where)
            token_mounts = [v for v in pod.get('volumes', []) if 'projected' in v and any('serviceAccountToken' in s for s in v['projected']['sources'])]
            require(bool(token_mounts) == (where == 'Deployment/ops-agent'), 'API token only for the ops agent: ' + where)
            for c in pod.get('containers', []) + pod.get('initContainers', []):
                sc = c.get('securityContext') or {}
                require(sc.get('allowPrivilegeEscalation') is False and sc.get('readOnlyRootFilesystem') is True
                        and sc.get('capabilities') == {'drop': ['ALL']} and not sc.get('privileged'), 'container security: ' + where)
                require(c['image'] in allowed_images, 'image not signed/registered: ' + where + ' ' + c['image'])
                require(not any('hostPort' in p for p in c.get('ports', [])), 'hostPort: ' + where)
                require('resources' in c and 'limits' in c['resources'], 'limits: ' + where)
                images_used.add(c['image'])
    roles = by_kind.get('Role', [])
    bindings = by_kind.get('RoleBinding', [])
    require(all(s == {'kind': 'ServiceAccount', 'name': 'ops-agent', 'namespace': 'ops'} for b in bindings for s in b['subjects']), 'only the ops agent is bound')
    for role in roles:
        for rule in role['rules']:
            verbs = set(rule['verbs'])
            require('*' not in verbs and '*' not in rule['resources'] and not {'create', 'delete', 'deletecollection', 'escalate', 'bind', 'impersonate'} & verbs, 'role verbs: ' + role['metadata']['name'])
            require(not {'secrets', 'pods/exec', 'pods/attach', 'pods/portforward'} & set(rule['resources']), 'role resources: ' + role['metadata']['name'])
            if verbs & {'patch', 'update'}:
                require(rule['resources'] == ['deployments'] and rule.get('resourceNames'), 'writes only to named deployments')
    fqdn = {(p['metadata']['namespace'], p['metadata']['name']): p for p in by_kind.get('FQDNNetworkPolicy', [])}
    require(set(fqdn) == {('platform', 'gateway-provider'), ('platform', 'redactor-provider')}, 'FQDN egress only for gateway and redactor')
    require(len(by_kind.get('ValidatingAdmissionPolicy', [])) == 1 and len(by_kind.get('ValidatingAdmissionPolicyBinding', [])) == 1, 'admission policy')
    return {'objects': len(docs), 'kinds': {k: len(v) for k, v in sorted(by_kind.items())}, 'images': sorted(images_used)}


def render(args, allow_pending=False):
    images = json.loads((HERE / 'images.json').read_text())
    text, refs = substitute(kustomize(args.kubectl), project_id=args.project_id, control_plane_cidr=args.control_plane_cidr,
                            gateway_gsa=args.gateway_gsa, redactor_gsa=args.redactor_gsa, images=images,
                            allow_pending=allow_pending)
    docs = [d for d in yaml.safe_load_all(text) if d]
    return text, validate(docs, refs)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-id', required=True)
    parser.add_argument('--control-plane-cidr', default='172.16.0.16/28')
    parser.add_argument('--gateway-gsa', required=True)
    parser.add_argument('--redactor-gsa', required=True)
    parser.add_argument('--kubectl', default='kubectl')
    parser.add_argument('--allow-pending', action='store_true', help='offline tests only: placeholder digests for unbuilt images')
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args(argv)
    try:
        text, summary = render(args, allow_pending=args.allow_pending)
    except (Rejected, KeyError, ValueError) as error:
        raise SystemExit('render:rejected:' + str(error))
    print(json.dumps(summary, sort_keys=True) if args.summary else text)


if __name__ == '__main__':
    main(sys.argv[1:])
