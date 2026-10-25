"""Repository-owned files: tracked files plus new, non-ignored source files.

Git's inventory is shared by validation and lint. Installed dependencies, caches
and generated output are not source; a tracked file is always checked even when
an ignore rule would hide an untracked file at the same path.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def files(root=ROOT):
    root = Path(root).resolve()
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError('repository source inventory unavailable')
    out = []
    for name in sorted(set(os.fsdecode(n) for n in result.stdout.split(b'\0') if n)):
        path = root / name
        if not path.resolve().is_relative_to(root):
            raise ValueError('source file resolves outside repository')
        if path.is_file():
            out.append(path)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suffix', action='append')
    parser.add_argument('--prefix')
    args = parser.parse_args()
    for path in files():
        relative = path.relative_to(ROOT)
        if args.suffix and path.suffix not in args.suffix:
            continue
        if args.prefix and not relative.is_relative_to(args.prefix):
            continue
        sys.stdout.buffer.write(os.fsencode(relative) + b'\0')


if __name__ == '__main__':
    main()
