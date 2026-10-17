"""Audit events: one JSON line on stdout with an "audit_event" field.

The cluster's log pipeline routes these lines to the audit log bucket (Cloud Logging sink on GKE). Nothing
is written to local files. Callers pass only bounded, non-content fields (no prompts, model text or secrets).
"""
import collections
import json
import sys
import threading
import time

_lock = threading.Lock()
RECENT = collections.deque(maxlen=50)  # this process's last lines, for the console (same bounded fields as stdout)
FORBIDDEN_FIELDS = frozenset({'text', 'prompt', 'content', 'token', 'key', 'secret', 'password', 'authorization'})


def recent(limit=50):
    with _lock:
        return list(RECENT)[-limit:]


def emit(event, component, stream=None, **fields):
    if any(name in FORBIDDEN_FIELDS for name in fields):
        raise ValueError('audit:content_field_rejected')
    line = json.dumps({'audit_event': event, 'component': component, 'at': round(time.time(), 3), **fields},
                      sort_keys=True, separators=(',', ':'), default=str)
    with _lock:
        if stream is None:
            RECENT.append(json.loads(line))
        (stream or sys.stdout).write(line + '\n')
        (stream or sys.stdout).flush()
