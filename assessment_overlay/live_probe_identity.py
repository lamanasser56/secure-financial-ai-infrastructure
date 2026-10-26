"""K05: only the disposable redactor may reach metadata identity and DLP TCP."""
import json
import re

from live_probe_kube import kubectl, one_pod, python_probe


REMOTE = r'''
import json, socket, urllib.error, urllib.request
request = urllib.request.Request(
    'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email',
    headers={'Metadata-Flavor':'Google'})
try:
    with urllib.request.urlopen(request, timeout=3) as response:
        email = response.read(256).decode()
except (OSError, urllib.error.HTTPError):
    email = None
try:
    connection = socket.create_connection(('dlp.us-east1.rep.googleapis.com',443), timeout=3)
    connection.close()
    dlp_tcp = True
except OSError:
    dlp_tcp = False
print(json.dumps({'expected_identity': email == '__EXPECTED_GSA__',
                  'no_identity': email is None, 'dlp_tcp': dlp_tcp}))
'''


def workload_identity_inventory(kubeconfig, project, *, executable='kubectl', run=kubectl):
    command = [str(executable), '--kubeconfig=' + str(kubeconfig),
               'get', 'serviceaccounts', '--all-namespaces', '-o', 'json']
    items = json.loads(run(command)).get('items', [])
    managed = {'platform', 'apps', 'ops', 'agent-financial', 'agent-platform-guide'}
    annotated = [(item['metadata']['namespace'], item['metadata']['name'],
                  item['metadata'].get('annotations', {}).get('iam.gke.io/gcp-service-account'))
                 for item in items if item['metadata']['namespace'] in managed
                 and item['metadata'].get('annotations', {}).get('iam.gke.io/gcp-service-account')]
    return annotated == [('platform', 'redactor',
                          'google-sdp-runtime@' + project + '.iam.gserviceaccount.com')]


def probe_k05(kubeconfig, project, *, executable='kubectl', pod=one_pod,
              execute=python_probe, inventory=workload_identity_inventory):
    if not re.fullmatch(r'sfai-assess-[a-z0-9-]{6,32}', project):
        raise ValueError('assessment:invalid_disposable_project')
    script = REMOTE.replace('__EXPECTED_GSA__',
                            'google-sdp-runtime@' + project + '.iam.gserviceaccount.com')
    checks = {}
    for label, namespace, selector in (
            ('redactor', 'platform', 'app.kubernetes.io/name=redactor'),
            ('app', 'apps', 'app.kubernetes.io/name=app'),
            ('worker', 'agent-financial', 'agent-platform/user-slot=u1')):
        name = pod(kubeconfig, namespace, selector, executable=executable)
        found = execute(kubeconfig, namespace, name, script, executable=executable)
        checks[label + '_identity'] = found['expected_identity'] if label == 'redactor' else found['no_identity']
        checks[label + '_dlp_tcp'] = found['dlp_tcp'] if label == 'redactor' else not found['dlp_tcp']
    checks['only_redactor_workload_identity_binding'] = inventory(kubeconfig, project, executable=executable)
    return checks
