"""Registered targets, read from the same ConfigMap that parameterises the admission policy.

Keys: "<namespace>.<deployment>.min|max|images|health". Only targets with all four keys exist; the agent can
neither observe nor change anything else (RBAC and the admission policy enforce the same set server-side).
"""
from dataclasses import dataclass
from pathlib import Path
import re

ACTIONS = ('restart', 'rollback', 'scale')
NAME = re.compile(r'[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?')


@dataclass(frozen=True)
class Target:
    namespace: str
    name: str
    min_replicas: int
    max_replicas: int
    images: tuple
    health: str | None

    @property
    def key(self):
        return self.namespace + '.' + self.name


def parse(data):
    groups = {}
    for key, value in data.items():
        parts = key.split('.')
        if len(parts) != 3 or parts[2] not in ('min', 'max', 'images', 'health'):
            raise ValueError('registry:key ' + key)
        groups.setdefault((parts[0], parts[1]), {})[parts[2]] = value
    targets = {}
    for (namespace, name), fields in sorted(groups.items()):
        if set(fields) != {'min', 'max', 'images', 'health'} or not NAME.fullmatch(namespace) or not NAME.fullmatch(name):
            raise ValueError('registry:incomplete ' + namespace + '.' + name)
        low, high = int(fields['min']), int(fields['max'])
        images = tuple(i for i in fields['images'].split(',') if i)
        if not 0 <= low <= high <= 5 or not images or not all('@sha256:' in i for i in images):
            raise ValueError('registry:bounds ' + namespace + '.' + name)
        health = None if fields['health'] == 'none' else fields['health']
        if health is not None and not re.fullmatch(r'http://[a-z0-9.-]+\.svc\.cluster\.local:\d+/[\w/.-]*', health):
            raise ValueError('registry:health ' + namespace + '.' + name)
        targets[namespace + '.' + name] = Target(namespace, name, low, high, images, health)
    return targets


def load(directory=Path('/registry')):
    return parse({p.name: p.read_text() for p in Path(directory).iterdir() if not p.name.startswith('.')})
