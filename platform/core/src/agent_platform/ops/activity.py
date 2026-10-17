"""Bounded masking activity from the redactor's own audit lines (read-only; uses the existing pods/log read right).

The redactor prints one audit line per request: {"audit_event":"redaction","caller":..., "categories":[...],"at":...}
or "redaction_failed" / "redaction_rejected". Lines are untrusted data: each is parsed against a closed shape, only
closed fields are kept, and nothing else from the line is returned. No text from a request is ever in these lines.
"""
import json
import re

from agent_platform.k8s import KubeError

NAMESPACE, SELECTOR, CONTAINER = 'platform', 'app.kubernetes.io/name=redactor', 'redactor'
CALLER = re.compile(r'[a-z0-9][a-z0-9-]{0,40}')
CATEGORY = re.compile(r'[A-Z][A-Z_]{1,40}')
TAIL, LIMIT, KEEP = 200, 16384, 20


def parse(text):
    events = []
    for line in text.splitlines()[-TAIL:]:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if type(value) is not dict or value.get('component') != 'redactor' or type(value.get('at')) not in (int, float):
            continue
        kind = {'redaction': 'masked', 'redaction_failed': 'blocked', 'redaction_rejected': 'blocked'}.get(value.get('audit_event'))
        caller = value.get('caller')
        if kind is None or (caller is not None and not (type(caller) is str and CALLER.fullmatch(caller))):
            continue
        categories = value.get('categories', [])
        if type(categories) is not list or not all(type(c) is str and CATEGORY.fullmatch(c) for c in categories):
            continue
        if kind == 'masked' and not categories:
            continue  # nothing was masked: not an event worth showing
        events.append({'kind': kind, 'at': round(float(value['at']), 3), 'source': 'redactor', 'caller': caller,
                       'categories': categories[:10],
                       'reason': 'redaction_unavailable' if value['audit_event'] == 'redaction_failed' else
                       'not_admitted' if kind == 'blocked' else None})
    return events[-KEEP:]


def recent(client):
    """{'events': [...], 'available': bool}: available is false when the redactor's log could not be read."""
    try:
        pods = client.list('pods', NAMESPACE, SELECTOR)
        if not pods:
            return {'events': [], 'available': False}
        return {'events': parse(client.logs(NAMESPACE, pods[0]['metadata']['name'], container=CONTAINER, tail=TAIL, limit=LIMIT)),
                'available': True}
    except KubeError:
        return {'events': [], 'available': False}
