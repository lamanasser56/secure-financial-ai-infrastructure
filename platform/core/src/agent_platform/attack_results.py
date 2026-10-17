"""The closed shape of attack-suite results that the console reads, shared by `make attack` (writer) and the console (reader).

Only the suite name, the completion time and, per case, its id, PASS/FAIL and start time survive: every value is matched
against a closed pattern, so no evidence detail, secret, project ID or free text can pass through, whatever the input holds.
`make attack` writes this shape into ConfigMap apps/attack-results; the front door mounts it read-only (no RBAC).
"""
import json
import re

CONFIGMAP, NAMESPACE, KEY = 'attack-results', 'apps', 'attack-suite.json'
SUITE = 'agent-platform-attacks'
CASE = re.compile(r'[a-z][a-z0-9_]{2,80}')  # no hyphen, dot or slash: a project ID, host or path cannot fit
TIME = re.compile(r'20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(\+00:00|Z)')
MAX_CASES = 64


def sanitize(data):
    """The closed shape, or ValueError. Input may be the full evidence report; everything else is dropped."""
    if type(data) is not dict or type(data.get('results')) is not list or not 0 < len(data['results']) <= MAX_CASES:
        raise ValueError('attack_results:shape')
    completed = data.get('completed_at')
    if type(completed) is not str or not TIME.fullmatch(completed):
        raise ValueError('attack_results:completed_at')
    rows = []
    for r in data['results']:
        if (type(r) is not dict or type(r.get('case')) is not str or not CASE.fullmatch(r['case']) or r.get('result') not in ('PASS', 'FAIL')
                or type(r.get('at')) is not str or not TIME.fullmatch(r['at'])):
            raise ValueError('attack_results:case')
        rows.append({'case': r['case'], 'result': r['result'], 'at': r['at']})
    return {'suite': SUITE, 'completed_at': completed, 'results': rows}


def configmap(data):
    """The ConfigMap that carries the sanitized results (nothing else) into the app's namespace."""
    return {'apiVersion': 'v1', 'kind': 'ConfigMap',
            'metadata': {'name': CONFIGMAP, 'namespace': NAMESPACE, 'labels': {'app.kubernetes.io/part-of': 'agent-platform'}},
            'data': {KEY: json.dumps(sanitize(data), sort_keys=True)}}
