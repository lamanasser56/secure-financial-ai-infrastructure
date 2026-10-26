"""Exact shared UI routes. The same source layout is copied into each Python image."""
from functools import lru_cache
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2] / 'ui'
ROUTE = re.compile(r'/(?:core\.js|style\.css|typeface/[a-z0-9-]+\.woff2)')


@lru_cache
def inventory(root=ROOT):
    value = json.loads((root / 'shared-assets.json').read_text())
    if (type(value) is not dict or set(value) != {'version', 'assets'} or value['version'] != 1
            or type(value['assets']) is not dict or not value['assets']):
        raise ValueError('shared UI inventory rejected')
    for route, kind in value['assets'].items():
        if not ROUTE.fullmatch(route) or kind not in {'text/javascript; charset=utf-8', 'text/css; charset=utf-8', 'font/woff2'}:
            raise ValueError('shared UI route rejected')
    return value['assets']


def read(route, *, root=ROOT):
    kind = inventory(root).get(route)
    if kind is None:
        return None
    file = (root / route[1:]).resolve()
    if not file.is_relative_to(root.resolve()) or not file.is_file():
        return None
    return file.read_bytes(), kind
