#!/usr/bin/env python3
"""Bounded read-only /proc visibility helper. Prints only active/complete flags."""
import argparse
import json
import os
from pathlib import Path
import stat
import time


def inspect(path):
    path = Path(path).absolute()
    if path.name != 'disposable-cache' or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError
    prefix, until, count = str(path) + '/', time.monotonic() + 2, 0
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            if not (proc / 'cmdline').read_bytes():
                continue
            for item in ('cwd', 'root'):
                value = os.readlink(proc / item)
                if value == str(path) or value.startswith(prefix):
                    return True
            for fd in (proc / 'fd').iterdir():
                count += 1
                if count > 16384 or time.monotonic() >= until:
                    raise ValueError
                value = os.readlink(fd).removesuffix(' (deleted)')
                if value == str(path) or value.startswith(prefix):
                    return True
            text = (proc / 'maps').read_text()
            if len(text) > 1048576:
                raise ValueError
            for line in text.splitlines():
                parts = line.split(None, 5)
                if len(parts) == 6 and parts[5].removesuffix(' (deleted)').startswith(prefix):
                    return True
        except (FileNotFoundError, ProcessLookupError):
            continue
    return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    try:
        value = {'complete': True, 'active': inspect(args.target)}
    except Exception:
        value = {'complete': False, 'active': None}
    print(json.dumps(value))
