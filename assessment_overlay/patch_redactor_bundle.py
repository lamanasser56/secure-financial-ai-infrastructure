"""Pure assessment-bundle transform for durable SDP limits and phone guard.

Produces a preseed stage and a later redactor Deployment stage. The caller
must wait for the seed Job to complete and read back both ledger files before
applying the Deployment. No cloud operation is performed here.
"""

from pathlib import Path
import re


def _one(docs, kind, namespace, name):
    found = [d for d in docs if d.get('kind') == kind and d.get('metadata', {}).get('namespace') == namespace
             and d.get('metadata', {}).get('name', '').startswith(name)]
    if len(found) != 1:
        raise ValueError('missing or duplicate ' + kind + '/' + namespace + '/' + name)
    return found[0]


def patch(docs, overlay_dir, run_id):
    if not re.fullmatch(r'assess-[0-9a-f]{16}', run_id):
        raise ValueError('fresh exact assessment run ID required')
    docs = list(docs)
    overlay = Path(overlay_dir)
    programs = _one(docs, 'ConfigMap', 'platform', 'platform-programs-')
    deployment = _one(docs, 'Deployment', 'platform', 'redactor')
    quota = _one(docs, 'ResourceQuota', 'platform', 'bounds')
    if 'phone_guard.py' not in programs['data'] or 'mask_phones' not in programs['data']['phone_guard.py']:
        raise ValueError('new phone guard absent from source render')
    if 'CompletedLedger' in programs['data']['redactor_server.py']:
        raise ValueError('redactor already transformed')
    programs['data']['redactor_server.py'] = (overlay / 'redactor_server.py').read_text()

    hard = quota['spec']['hard']
    if (hard['persistentvolumeclaims'], hard['requests.storage']) == ('1', '10Gi'):
        hard['persistentvolumeclaims'], hard['requests.storage'] = '2', '11Gi'
    elif (hard['persistentvolumeclaims'], hard['requests.storage']) != ('2', '11Gi'):
        raise ValueError('unexpected platform storage quota')

    container = deployment['spec']['template']['spec']['containers'][0]
    if container['name'] != 'redactor' or any(v['name'] == 'assessment-state' for v in container.get('volumeMounts', [])):
        raise ValueError('unexpected redactor Deployment')
    image = container['image']
    if any(v['name'] == 'ASSESSMENT_RUN_ID' for v in container.get('env', [])):
        raise ValueError('assessment run ID already set')
    container.setdefault('env', []).append({'name': 'ASSESSMENT_RUN_ID', 'value': run_id})
    container.setdefault('volumeMounts', []).extend((
        {'name': 'assessment-guard', 'mountPath': '/assessment', 'readOnly': True},
        {'name': 'assessment-state', 'mountPath': '/assessment-state'},
    ))
    deployment['spec']['template']['spec'].setdefault('volumes', []).extend((
        {'name': 'assessment-guard', 'configMap': {'name': 'assessment-sdp-guard', 'defaultMode': 292}},
        {'name': 'assessment-state', 'persistentVolumeClaim': {'claimName': 'assessment-sdp-attempts'}},
    ))
    guard = {'apiVersion': 'v1', 'kind': 'ConfigMap',
             'metadata': {'name': 'assessment-sdp-guard', 'namespace': 'platform'},
             'data': {'sdp_guard.py': (overlay / 'sdp_guard.py').read_text(),
                      'seed_sdp.py': (overlay / 'seed_sdp.py').read_text()}}
    claim = {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim',
             'metadata': {'name': 'assessment-sdp-attempts', 'namespace': 'platform'},
             'spec': {'accessModes': ['ReadWriteOnce'], 'storageClassName': 'agent-runtime-disposable',
                      'resources': {'requests': {'storage': '1Gi'}}}}
    job = {'apiVersion': 'batch/v1', 'kind': 'Job',
           'metadata': {'name': 'assessment-sdp-seed', 'namespace': 'platform'},
           'spec': {'backoffLimit': 0, 'template': {'spec': {
               'automountServiceAccountToken': False, 'restartPolicy': 'Never',
               'serviceAccountName': 'redactor',
               'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532,
                                   'runAsGroup': 65532, 'fsGroup': 65532},
               'containers': [{'name': 'seed', 'image': image,
                               'command': ['/usr/local/bin/python3.12', '/assessment/seed_sdp.py', '/assessment-state'],
                               'env': [{'name': 'ASSESSMENT_RUN_ID', 'value': run_id}],
                               'securityContext': {'allowPrivilegeEscalation': False,
                                                   'readOnlyRootFilesystem': True,
                                                   'capabilities': {'drop': ['ALL']}},
                               'volumeMounts': [{'name': 'assessment-guard', 'mountPath': '/assessment', 'readOnly': True},
                                                {'name': 'assessment-state', 'mountPath': '/assessment-state'}]}],
               'volumes': [{'name': 'assessment-guard', 'configMap': {'name': 'assessment-sdp-guard', 'defaultMode': 292}},
                           {'name': 'assessment-state', 'persistentVolumeClaim': {'claimName': 'assessment-sdp-attempts'}}],
           }}}}
    if any(d.get('metadata', {}).get('name') in ('assessment-sdp-guard', 'assessment-sdp-attempts',
                                                'assessment-sdp-seed') for d in docs):
        raise ValueError('assessment SDP resources already exist')
    docs[docs.index(deployment):docs.index(deployment)] = [guard, claim, job]
    return docs, [guard, claim, job], deployment
