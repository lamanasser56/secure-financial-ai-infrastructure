#!/usr/bin/env python3
"""Offline exact proposed Kubernetes bundle. Never applies or grants admission.

Image provenance, private admissions, native schema and saved cloud plans are
separate gates. Validate by regenerating the complete canonical object list.
Secrets are referenced by fixed names; their values are never rendered here.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
NS = 'google-agent-demo'
ACK = 'I_ACKNOWLEDGE_ONE_FIXED_SYNTHETIC_CATALOG_NO_AGENT_PROMOTION'
SDP_DIGEST = '667ceec4b8290df1341a91a7685ad140319fca6d23f92b9948dddf9fac64136b'


def obj(kind, name, spec=None, api='v1', **fields):
    value = {'apiVersion': api, 'kind': kind, 'metadata': {'name': name, 'namespace': NS}}
    if spec is not None:
        value['spec'] = spec
    return value | fields


def code(name):
    raw = (ROOT / 'scripts' / name).read_bytes()
    if not 0 < len(raw) <= 32768:
        raise ValueError
    return raw.decode('utf-8')


def bundle(project, gateway, application, database):
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', project):
        raise ValueError
    prefix = f'us-east1-docker.pkg.dev/{project}/sdp-evaluation-images/'
    for image, name in ((gateway, 'agent-demo-gateway'), (application, 'agent-demo-application'),
                        (database, 'agent-demo-database')):
        if not re.fullmatch(re.escape(prefix + name) + r'@sha256:[a-f0-9]{64}', image):
            raise ValueError
    redactor = prefix + 'google-sdp-context@sha256:' + SDP_DIGEST
    namespace = obj('Namespace', NS)
    namespace['metadata'].pop('namespace')
    namespace['metadata']['labels'] = {'pod-security.kubernetes.io/enforce': 'restricted'}
    # NetworkLogging delegates deny logging: denials are logged only in namespaces carrying this annotation.
    namespace['metadata']['annotations'] = {'policy.network.gke.io/enable-deny-logging': 'true'}
    result = [namespace]
    for name in ('application', 'gateway', 'redactor', 'database', 'bootstrap'):
        sa = obj('ServiceAccount', 'google-agent-demo-' + name, automountServiceAccountToken=False)
        if name in {'gateway', 'redactor'}:
            gsa = 'google-agent-demo-model' if name == 'gateway' else 'google-sdp-runtime'
            sa['metadata']['annotations'] = {'iam.gke.io/gcp-service-account': f'{gsa}@{project}.iam.gserviceaccount.com'}
        result.append(sa)
    data = {name: (ROOT / path).read_text() for name, path in {
        'litellm-vertex.yaml': 'deploy/local-agents/litellm-vertex.yaml',
        'litellm-schema.sql': 'deploy/local-agents/litellm-schema.sql',
        'tenant.sql': 'deploy/local-agents/tenant.sql', 'expenses.json': 'demo/fixtures/expenses.json',
        'synthetic-demo.json': 'evaluation/agent-composition/synthetic-demo.json'}.items()}
    result.append(obj('ConfigMap', 'demo-configuration', data=data))
    security = {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                'capabilities': {'drop': ['ALL']}, 'seccompProfile': {'type': 'RuntimeDefault'}}

    def workload(name, image, program, secret, *, phase=None, job=False, memory_request='128Mi'):
        args = ['-c', code(program)] + ([] if phase is None else [phase])
        annotations = {'portfolio.example/program-sha256': hashlib.sha256(args[1].encode()).hexdigest()}
        container = {'name': name, 'image': image, 'command': ['/usr/local/bin/python3.12'],
            'args': args, 'securityContext': copy.deepcopy(security),
            'resources': {'requests': {'cpu': '100m', 'memory': memory_request},
                          'limits': {'cpu': '1000m', 'memory': '768Mi'}},
            'env': [{'name': 'PORTFOLIO_SYNTHETIC_LIVE_DEMO_ACK', 'value': ACK}],
            'volumeMounts': [{'name': 'admission', 'mountPath': '/admission', 'subPath': 'private', 'readOnly': True},
                             {'name': 'state', 'mountPath': '/state', 'subPath': 'private'},
                             {'name': 'configuration', 'mountPath': '/configuration', 'readOnly': True},
                             {'name': 'temporary', 'mountPath': '/tmp'}]}
        init = {'name': 'stage-private-admission', 'image': application,
            'command': ['/usr/local/bin/python3.12'], 'args': ['-c', code('stage-synthetic-demo-admission.py')],
            'securityContext': copy.deepcopy(security),
            'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'}, 'limits': {'cpu': '200m', 'memory': '128Mi'}},
            'volumeMounts': [{'name': 'projected', 'mountPath': '/projected', 'readOnly': True},
                             {'name': 'admission', 'mountPath': '/staging'},
                             {'name': 'state', 'mountPath': '/state-staging'}]}
        pod = {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
               'serviceAccountName': 'google-agent-demo-' + ('application' if name == 'catalog' else 'bootstrap' if name.startswith('bootstrap') else name),
               'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532, 'fsGroup': 65532,
                                   'seccompProfile': {'type': 'RuntimeDefault'}},
               'initContainers': [init], 'containers': [container], 'activeDeadlineSeconds': 900,
               'volumes': [{'name': 'projected', 'secret': {'secretName': secret, 'defaultMode': 288}},
                           {'name': 'admission', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '1Mi'}},
                           {'name': 'state', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '32Mi'}},
                           {'name': 'configuration', 'configMap': {'name': 'demo-configuration'}},
                           {'name': 'temporary', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '64Mi'}}]}
        metadata = {'labels': {'app': name}, 'annotations': annotations}
        if job:
            return obj('Job', name, {'suspend': True, 'backoffLimit': 0, 'parallelism': 1, 'completions': 1,
                'activeDeadlineSeconds': 900, 'ttlSecondsAfterFinished': 3600,
                'template': {'metadata': metadata, 'spec': pod}}, api='batch/v1')
        value = obj('Pod', name, pod); value['metadata'].update(metadata); return value

    # Measured gateway working set ~512 MiB (startup peak ~517 MiB) once the Prisma CLI path is disabled.
    result += [workload('gateway', gateway, 'supervise-synthetic-demo-gateway.py', 'gateway-admission', memory_request='512Mi'),
               workload('redactor', redactor, 'serve-synthetic-demo-redactor.py', 'redactor-admission'),
               workload('catalog', application, 'run-synthetic-live-catalog.py', 'application-admission', job=True),
               workload('bootstrap-database', application, 'bootstrap-synthetic-demo.py', 'bootstrap-admission', phase='--database', job=True),
               workload('bootstrap-clients', application, 'bootstrap-synthetic-demo.py', 'bootstrap-admission', phase='--clients', job=True)]
    result.append(obj('Pod', 'database', {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
        'activeDeadlineSeconds': 900, 'serviceAccountName': 'google-agent-demo-database',
        'securityContext': {'runAsNonRoot': True, 'runAsUser': 70, 'runAsGroup': 70, 'fsGroup': 70,
                            'seccompProfile': {'type': 'RuntimeDefault'}},
        'containers': [{'name': 'database', 'image': database, 'securityContext': security,
            'args': ['postgres', '-c', 'log_statement=none', '-c', 'log_min_error_statement=panic'],
            'env': [{'name': 'PGDATA', 'value': '/var/lib/postgresql/data/pgdata'},
                    {'name': 'POSTGRES_PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'database-owner', 'key': 'password'}}}],
            'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'}, 'limits': {'cpu': '1000m', 'memory': '512Mi'}},
            'volumeMounts': [{'name': 'data', 'mountPath': '/var/lib/postgresql/data'},
                             {'name': 'socket', 'mountPath': '/var/run/postgresql'}]}],
        'volumes': [{'name': 'data', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '256Mi'}},
                    {'name': 'socket', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '8Mi'}}]}))
    for name, port in (('database', 5432), ('gateway', 4000), ('redactor', 4003)):
        result.append(obj('Service', name, {'type': 'ClusterIP', 'selector': {'app': name},
            'ports': [{'port': port, 'targetPort': port, 'protocol': 'TCP'}]}))
    result[-4]['metadata']['labels'] = {'app': 'database'}
    result.append(obj('ResourceQuota', 'demo-bounds', {'hard': {'pods': '6', 'count/jobs.batch': '3',
        'requests.cpu': '1500m', 'limits.cpu': '6000m', 'requests.memory': '2Gi', 'limits.memory': '5Gi'}}))
    result.append(obj('LimitRange', 'demo-limits', {'limits': [{'type': 'Container',
        'max': {'cpu': '1000m', 'memory': '768Mi'}, 'default': {'cpu': '1000m', 'memory': '768Mi'},
        'defaultRequest': {'cpu': '100m', 'memory': '128Mi'}}]}))
    result.append(obj('NetworkPolicy', 'deny-all', {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress']}, api='networking.k8s.io/v1'))
    for name in ('catalog', 'gateway', 'redactor', 'database', 'bootstrap-database', 'bootstrap-clients'):
        egress = []
        ingress = []
        if name != 'database':
            egress.append({'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                                  'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
                           'ports': [{'protocol': p, 'port': 53} for p in ('TCP', 'UDP')]})
        destinations = {'catalog': [('gateway', 4000), ('database', 5432), ('redactor', 4003)],
                        'gateway': [('database', 5432)], 'bootstrap-database': [('database', 5432)],
                        'bootstrap-clients': [('gateway', 4000)]}.get(name, [])
        for target, port in destinations:
            egress.append({'to': [{'podSelector': {'matchLabels': {'app': target}}}], 'ports': [{'protocol': 'TCP', 'port': port}]})
        if name in {'gateway', 'redactor'}:
            egress.append({'to': [{'ipBlock': {'cidr': '169.254.169.254/32'}}], 'ports': [{'protocol': 'TCP', 'port': 80}]})
        sources = {'database': ['catalog', 'gateway', 'bootstrap-database'],
                   'gateway': ['catalog', 'bootstrap-clients'], 'redactor': ['catalog']}.get(name, [])
        if sources:
            port = {'database': 5432, 'gateway': 4000, 'redactor': 4003}[name]
            ingress = [{'from': [{'podSelector': {'matchLabels': {'app': source}}} for source in sources],
                        'ports': [{'protocol': 'TCP', 'port': port}]}]
        result.append(obj('NetworkPolicy', name, {'podSelector': {'matchLabels': {'app': name}},
            'policyTypes': ['Ingress', 'Egress'], 'ingress': ingress, 'egress': egress}, api='networking.k8s.io/v1'))
    for name, endpoint in (('gateway', 'us-east1-aiplatform.googleapis.com'), ('redactor', 'dlp.us-east1.rep.googleapis.com')):
        policy = obj('FQDNNetworkPolicy', name + '-regional', {'podSelector': {'matchLabels': {'app': name}},
            'egress': [{'matches': [{'name': endpoint}], 'ports': [{'protocol': 'TCP', 'port': 443}]}]}, api='networking.gke.io/v1alpha1')
        policy['metadata']['annotations'] = {'policy.network.gke.io/enable-logging': 'true'}
        result.append(policy)
        probe = (ROOT / 'scripts/probe-google-sdp-egress.py').read_text()
        if name == 'gateway':
            probe = probe.replace('dlp.us-east1.rep.googleapis.com', endpoint).replace('google-sdp-runtime@', 'google-agent-demo-model@')
        pod = {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
            'serviceAccountName': 'google-agent-demo-' + name,
            'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532,
                                'seccompProfile': {'type': 'RuntimeDefault'}},
            'containers': [{'name': 'probe', 'image': redactor,
                'command': ['/usr/local/bin/python3.12'], 'args': ['-c', probe, '--network-preflight'],
                'securityContext': copy.deepcopy(security),
                'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'}, 'limits': {'cpu': '500m', 'memory': '512Mi'}},
                'env': [{'name': 'PORTFOLIO_GOOGLE_SDP_NETWORK_PREFLIGHT_ACK', 'value': 'I_ACKNOWLEDGE_SYNTHETIC_NETWORK_PREFLIGHT'},
                        {'name': 'PORTFOLIO_GOOGLE_SDP_EXPECTED_GSA', 'value': ('google-agent-demo-model' if name == 'gateway' else 'google-sdp-runtime') + '@' + project + '.iam.gserviceaccount.com'}]}]}
        result.append(obj('Job', name + '-network-preflight', {'suspend': True, 'backoffLimit': 0,
            'parallelism': 1, 'completions': 1, 'activeDeadlineSeconds': 120, 'ttlSecondsAfterFinished': 3600,
            'template': {'metadata': {'labels': {'app': name, 'demo-probe': 'true'},
                                      'annotations': {'portfolio.example/program-sha256': hashlib.sha256(probe.encode()).hexdigest()}},
                         'spec': pod}}, api='batch/v1'))
    app_probe = code('probe-synthetic-demo-application-egress.py')
    result.append(obj('Job', 'application-network-preflight', {'suspend': True, 'backoffLimit': 0,
        'parallelism': 1, 'completions': 1, 'activeDeadlineSeconds': 120, 'ttlSecondsAfterFinished': 3600,
        'template': {'metadata': {'labels': {'app': 'catalog', 'demo-probe': 'true'},
                                  'annotations': {'portfolio.example/program-sha256': hashlib.sha256(app_probe.encode()).hexdigest()}},
                     'spec': {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
                        'serviceAccountName': 'google-agent-demo-application',
                        'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532,
                                            'seccompProfile': {'type': 'RuntimeDefault'}},
                        'containers': [{'name': 'probe', 'image': application,
                            'command': ['/usr/local/bin/python3.12'], 'args': ['-c', app_probe],
                            'securityContext': copy.deepcopy(security),
                            'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'},
                                          'limits': {'cpu': '500m', 'memory': '512Mi'}}}]}}}, api='batch/v1'))
    logging = obj('NetworkLogging', 'default', {'cluster': {'allow': {'log': True, 'delegate': True},
                                                          'deny': {'log': True, 'delegate': True}}},
                  api='networking.gke.io/v1alpha1')
    logging['metadata'].pop('namespace')
    result.append(logging)
    for item in result:
        if item['kind'] == 'NetworkPolicy':
            item['metadata']['annotations'] = {'policy.network.gke.io/enable-logging': 'true'}
    return {'apiVersion': 'v1', 'kind': 'List', 'items': result}


def validate_document(actual, expected):
    if actual != expected:
        raise ValueError('demo:noncanonical_objects')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    for name in ('gateway', 'application', 'database'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--validate', type=Path)
    args = parser.parse_args()
    expected = bundle(args.project, args.gateway, args.application, args.database)
    if args.validate:
        if args.validate.is_symlink() or not args.validate.is_file() or args.validate.stat().st_size > 262144:
            raise ValueError
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError
                value[key] = item
            return value
        validate_document(json.loads(args.validate.read_bytes().decode('utf-8'), object_pairs_hook=unique), expected)
        print('PASS: exact proposed synthetic bundle; provenance/admission not inferred')
    else:
        print(json.dumps(expected, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('demo:deployment_contract_rejected') from None
