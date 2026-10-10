"""Minimal in-cluster Kubernetes API client (stdlib only).

Exposes exactly what the ops agent needs: GET/LIST of namespaced objects, pod logs (bounded), and one
merge-PATCH of a Deployment. There is deliberately no create, delete, exec, attach or port-forward function.
The projected service-account token is re-read on every request (it rotates).
"""
import json
from pathlib import Path
import ssl
import urllib.error
import urllib.parse
import urllib.request

SA = Path('/var/run/secrets/kubernetes.io/serviceaccount')
API = 'https://kubernetes.default.svc'
PATHS = {'pods': '/api/v1/namespaces/{ns}/pods', 'events': '/api/v1/namespaces/{ns}/events',
         'services': '/api/v1/namespaces/{ns}/services',
         'deployments': '/apis/apps/v1/namespaces/{ns}/deployments', 'replicasets': '/apis/apps/v1/namespaces/{ns}/replicasets',
         'statefulsets': '/apis/apps/v1/namespaces/{ns}/statefulsets',
         'networkpolicies': '/apis/networking.k8s.io/v1/namespaces/{ns}/networkpolicies',
         'rolebindings': '/apis/rbac.authorization.k8s.io/v1/namespaces/{ns}/rolebindings',
         'roles': '/apis/rbac.authorization.k8s.io/v1/namespaces/{ns}/roles'}


class KubeError(Exception):
    def __init__(self, status, reason):
        super().__init__(f'{status}:{reason}')
        self.status, self.reason = status, reason


class Client:
    def __init__(self, *, api=API, token_path=SA / 'token', ca_path=SA / 'ca.crt', opener=None, timeout=10):
        self._api, self._token_path, self._timeout = api, Path(token_path), timeout
        if opener is None:
            context = ssl.create_default_context(cafile=str(ca_path))
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context)).open
        self._open = opener

    def _request(self, method, path, body=None, content_type=None, raw=False, limit=4 << 20):
        headers = {'Authorization': 'Bearer ' + self._token_path.read_text().strip(), 'Accept': 'application/json'}
        if content_type:
            headers['Content-Type'] = content_type
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self._api + path, data=data, method=method, headers=headers)
        try:
            with self._open(request, timeout=self._timeout) as response:
                payload = response.read(limit + 1)
        except urllib.error.HTTPError as error:
            try:
                reason = json.loads(error.read(65536)).get('reason', 'Unknown')
            except Exception:
                reason = 'Unknown'
            raise KubeError(error.code, reason) from None
        except (urllib.error.URLError, OSError):
            raise KubeError(0, 'Unavailable') from None
        if len(payload) > limit:
            raise KubeError(0, 'ResponseTooLarge')
        return payload.decode('utf-8', 'replace') if raw else json.loads(payload)

    def list(self, kind, namespace, selector=None):
        query = '?' + urllib.parse.urlencode({'labelSelector': selector}) if selector else ''
        return self._request('GET', PATHS[kind].format(ns=namespace) + query)['items']

    def get(self, kind, namespace, name):
        return self._request('GET', PATHS[kind].format(ns=namespace) + '/' + urllib.parse.quote(name, safe=''))

    def logs(self, namespace, pod, *, container=None, tail=50, limit=16384):
        query = {'tailLines': str(tail), 'limitBytes': str(limit)}
        if container:
            query['container'] = container
        return self._request('GET', PATHS['pods'].format(ns=namespace) + '/' + urllib.parse.quote(pod, safe='')
                             + '/log?' + urllib.parse.urlencode(query), raw=True, limit=limit)

    def patch_deployment(self, namespace, name, patch):
        return self._request('PATCH', PATHS['deployments'].format(ns=namespace) + '/' + urllib.parse.quote(name, safe=''),
                             patch, content_type='application/merge-patch+json')
