"""One-time seed for a newly registered assessment PVC; never resets prior state."""

import json
import os
from pathlib import Path
import sys


def seed(directory):
    from sdp_guard import RUN

    root = Path(directory)
    if not root.is_dir():
        raise RuntimeError('assessment state volume missing')
    states = {
        'sdp-attempts.json': {'run_id': RUN, 'limit': 60, 'used': 0},
        'sdp-completions.json': {'run_id': RUN, 'limit': 20, 'completed': 0, 'inflight': []},
    }
    if any((root / name).exists() for name in states):
        raise RuntimeError('assessment state already initialized; reset forbidden')
    for name, state in states.items():
        fd = os.open(root / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(state, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
    dfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: seed_sdp.py STATE_DIR')
    seed(sys.argv[1])
