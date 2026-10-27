"""Private record of failed cloud commands, with one masked reason line on stderr.

The full command, exit code and stderr of a failed gcloud, Terraform, crane,
cosign or kubectl call go to `logs/cloud-failures.jsonl` in the private run
folder (mode 0600); they are never printed. The printed line keeps only the
command's first words and the first error line, with project IDs, project
numbers, billing accounts, emails and service accounts masked. A repeat of
the same reason (a poll that keeps failing) is printed once.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys


LOG_NAME = 'cloud-failures.jsonl'
_state = {'directory': None, 'secrets': (), 'last': None}
_PATTERNS = (
    (re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'), '<EMAIL>'),
    (re.compile(r'\b[A-F0-9]{6}-[A-F0-9]{6}-[A-F0-9]{6}\b'), '<BILLING>'),
    (re.compile(r'\bprojects/[a-z][a-z0-9-]{4,28}[a-z0-9]\b'), 'projects/<PROJECT>'),
    (re.compile(r'\b(?:sfai-assess|project)-[a-z0-9-]{4,30}\b'), '<PROJECT>'),
    (re.compile(r'\b[0-9]{6,}\b'), '<NUM>'),
)


def configure(run_dir, manifest=None):
    """Log into this private run folder; mask the run's own project identifiers."""
    directory = Path(run_dir) / 'logs'
    directory.mkdir(mode=0o700, exist_ok=True)
    secrets = set()
    if manifest:
        secrets.add(manifest.get('disposable_project_id') or '')
        match = re.search(r'pkg\.dev/([^/]+)/', manifest.get('source_registry') or '')
        if match:
            secrets.add(match[1])
    _state.update(directory=directory, secrets=tuple(sorted(filter(None, secrets), key=len, reverse=True)),
                  last=None)


def mask(text):
    # Whole emails (including service accounts) first, before any part is replaced.
    pattern, replacement = _PATTERNS[0]
    text = pattern.sub(replacement, text)
    for secret in _state['secrets']:
        text = text.replace(secret, '<PROJECT>')
    for pattern, replacement in _PATTERNS[1:]:
        text = pattern.sub(replacement, text)
    return text


def reason(argv, returncode, stderr):
    words = [Path(str(argv[0])).name] + [str(word) for word in argv[1:4] if not str(word).startswith('-')]
    lines = [line.strip() for line in (stderr or '').splitlines() if line.strip()]
    first = next((line for line in lines if 'ERROR' in line or 'Error' in line), lines[-1] if lines else '')
    return mask('cloud-failure: %s rc=%s: %s' % (' '.join(words), returncode, first))[:300]


def failed(argv, returncode, stderr, *, stream=None):
    """Record one failed command privately and print its masked reason once."""
    directory = _state['directory']
    if directory is not None:
        record = {'at': datetime.now(timezone.utc).isoformat(), 'argv': [str(word) for word in argv],
                  'returncode': returncode, 'stderr': stderr or ''}
        path = directory / LOG_NAME
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), 'a') as log:
            log.write(json.dumps(record) + '\n')
    line = reason(argv, returncode, stderr)
    if line != _state['last']:
        _state['last'] = line
        print(line, file=stream or sys.stderr, flush=True)
    return line
