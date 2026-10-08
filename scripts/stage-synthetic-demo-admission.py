#!/usr/bin/env python3
"""Copy a fixed projected Secret into an owned private emptyDir.

Kubernetes projected files are platform-owned. The main process only reads its
own 0600 copies. This init program admits no command, text or download selector.
It is separately hashed in the exact rendered bundle.
"""
import os
from pathlib import Path
import stat
import sys


def stage():
    source, destination = Path('/projected'), Path('/staging/private')
    for directory in (destination, Path('/state-staging/private')):
        directory.mkdir(mode=0o700)
        # fsGroup makes the kubelet mark volume directories setgid, and new directories inherit it; the
        # readers require exactly 0700, so the mode is set explicitly instead of relying on mkdir.
        os.chmod(directory, 0o700)
    files = {'run.json', 'redactor-server.json', 'gateway.json', 'bootstrap.json',
             'application-alpha.json', 'application-beta.json', 'redactor-client.json',
             'synthetic-demo.json', 'litellm-vertex.yaml'}
    copied = 0
    for path in source.iterdir():
        if path.name.startswith('..'):
            continue  # Platform projection metadata, never copied.
        if path.name not in files:
            raise ValueError
        resolved = path.resolve(strict=True)
        if source.resolve() not in resolved.parents:
            raise ValueError
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 32768:
            raise ValueError
        fd = os.open(destination / path.name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as out:
            out.write(resolved.read_bytes()); out.flush(); os.fsync(out.fileno())
        copied += 1
    if not copied:
        raise ValueError
    directory = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) != 1:
        raise SystemExit('admission:arguments_rejected')
    try:
        stage()
    except Exception:
        raise SystemExit('admission:private_projection_rejected') from None
