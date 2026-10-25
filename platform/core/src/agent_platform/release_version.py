"""Public image source identity; an unknown version must never be replaced with latest main."""
import os
import re


def source_commit(value=None):
    if value is None:
        value = os.environ.get('PLATFORM_SOURCE_COMMIT', '')
    return value if isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}', value) else None
