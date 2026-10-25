"""Assessment-only LiteLLM route to a private, fixed in-cluster provider.

The gateway image and gateway_entry.py remain unchanged. This transform changes
only the generated route ConfigMap, removes its Vertex egress policy, and adds
the minimum stub workload and mutual network policies in the disposable bundle.
"""

import copy
import hashlib
from pathlib import Path

import yaml


STUB_URL = 'http://provider-stub.assess-probes.svc.cluster.local:8080/v1'


def one(docs, kind, namespace, name_prefix):
    found = [doc for doc in docs if doc['kind'] == kind
             and doc['metadata'].get('namespace', '') == namespace
             and doc['metadata']['name'].startswith(name_prefix)]
    if len(found) != 1:
        raise ValueError('missing or duplicate ' + kind + '/' + namespace + '/' + name_prefix)
    return found[0]


def patch(docs, stub_image, source_path=Path(__file__).with_name('provider_stub.py')):
    docs = copy.deepcopy(docs)
    if (not stub_image.startswith('us-east1-docker.pkg.dev/')
            or '@sha256:' not in stub_image):
        raise ValueError('stub must use a qualified image digest')
    route = one(docs, 'ConfigMap', 'platform', 'gateway-config-')
    original = route['data']['litellm.yaml']
    config = yaml.safe_load(original)
    if (len(config['model_list']) != 1
            or config['model_list'][0]['model_name'] != 'secure-financial-chat'
            or config['model_list'][0]['litellm_params']['model'] != 'vertex_ai/gemini-3.5-flash'
            or config['litellm_settings']['num_retries'] != 0
            or config['router_settings']['num_retries'] != 0
            or any(config['router_settings'][name] for name in
                   ('fallbacks', 'context_window_fallbacks', 'content_policy_fallbacks'))):
        raise ValueError('unexpected main gateway route')
    params = config['model_list'][0]['litellm_params']
    if params.get('max_retries') != 0 or params.get('timeout') != 8:
        raise ValueError('main gateway retry/timeout drift')
    config['model_list'][0]['litellm_params'] = {
        'model': 'openai/assessment-stub', 'api_base': STUB_URL,
        'api_key': 'synthetic-assessment-only', 'max_retries': 0, 'timeout': 8,
        'input_cost_per_token': 0, 'output_cost_per_token': 0,
    }
    route['data']['litellm.yaml'] = (
        '# ASSESSMENT ONLY: fixed private provider, zero external LLM calls.\n'
        + yaml.safe_dump(config, sort_keys=True))
    if 'vertex_ai/' in route['data']['litellm.yaml']:
        raise ValueError('external model route retained')
    provider_egress = one(docs, 'FQDNNetworkPolicy', 'platform', 'gateway-provider')
    docs.remove(provider_egress)
    source = Path(source_path).read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    if any(doc['metadata']['name'] == 'assess-probes' and doc['kind'] == 'Namespace'
           for doc in docs):
        raise ValueError('assessment probe namespace already exists')
    docs.extend([
        {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'assess-probes',
            'labels': {'pod-security.kubernetes.io/enforce': 'restricted'}}},
        {'apiVersion': 'v1', 'kind': 'ResourceQuota',
         'metadata': {'namespace': 'assess-probes', 'name': 'assessment-quota'},
         'spec': {'hard': {'pods': '2', 'services.loadbalancers': '0',
                           'services.nodeports': '0', 'requests.cpu': '250m',
                           'requests.memory': '256Mi', 'limits.cpu': '500m',
                           'limits.memory': '512Mi'}}},
        {'apiVersion': 'v1', 'kind': 'ServiceAccount',
         'metadata': {'namespace': 'assess-probes', 'name': 'provider-stub'},
         'automountServiceAccountToken': False},
        {'apiVersion': 'v1', 'kind': 'ConfigMap',
         'metadata': {'namespace': 'assess-probes', 'name': 'provider-stub-code',
                      'annotations': {'assessment/source-sha256': source_hash}},
         'data': {'provider_stub.py': source.decode('utf-8')}},
        {'apiVersion': 'apps/v1', 'kind': 'Deployment',
         'metadata': {'namespace': 'assess-probes', 'name': 'provider-stub'},
         'spec': {'replicas': 1,
                  'selector': {'matchLabels': {'assessment.role': 'provider-stub'}},
                  'template': {'metadata': {'labels': {'assessment.role': 'provider-stub'}},
                   'spec': {'serviceAccountName': 'provider-stub',
                    'automountServiceAccountToken': False,
                    'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532,
                        'runAsGroup': 65532, 'seccompProfile': {'type': 'RuntimeDefault'}},
                    'containers': [{'name': 'provider-stub', 'image': stub_image,
                        'command': ['/usr/local/bin/python3.12', '-u', '/assessment/provider_stub.py'],
                        'ports': [{'containerPort': 8080, 'name': 'http'}],
                        'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'},
                                      'limits': {'cpu': '100m', 'memory': '128Mi'}},
                        'securityContext': {'allowPrivilegeEscalation': False,
                            'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                        'volumeMounts': [{'name': 'code', 'mountPath': '/assessment',
                                          'readOnly': True}]}],
                    'volumes': [{'name': 'code', 'configMap': {'name': 'provider-stub-code',
                                                             'defaultMode': 292}}]}}}},
        {'apiVersion': 'v1', 'kind': 'Service',
         'metadata': {'namespace': 'assess-probes', 'name': 'provider-stub'},
         'spec': {'type': 'ClusterIP', 'selector': {'assessment.role': 'provider-stub'},
                  'ports': [{'port': 8080, 'targetPort': 8080}]}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'namespace': 'assess-probes', 'name': 'default-deny'},
         'spec': {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress']}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'namespace': 'assess-probes', 'name': 'allow-gateway-only'},
         'spec': {'podSelector': {'matchLabels': {'assessment.role': 'provider-stub'}},
                  'policyTypes': ['Ingress'],
                  'ingress': [{'from': [{'namespaceSelector': {'matchLabels':
                      {'kubernetes.io/metadata.name': 'platform'}},
                      'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'gateway'}}}],
                      'ports': [{'protocol': 'TCP', 'port': 8080}]}]}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'namespace': 'platform', 'name': 'gateway-to-private-stub'},
         'spec': {'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'gateway'}},
                  'policyTypes': ['Egress'],
                  'egress': [{'to': [{'namespaceSelector': {'matchLabels':
                      {'kubernetes.io/metadata.name': 'assess-probes'}},
                      'podSelector': {'matchLabels': {'assessment.role': 'provider-stub'}}}],
                      'ports': [{'protocol': 'TCP', 'port': 8080}]}]}},
    ])
    return docs, {'main_route_sha256': hashlib.sha256(original.encode()).hexdigest(),
                  'stub_source_sha256': source_hash,
                  'patched_route_sha256': hashlib.sha256(route['data']['litellm.yaml'].encode()).hexdigest(),
                  'stub_image': stub_image}
