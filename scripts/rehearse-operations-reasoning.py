#!/usr/bin/env python3
"""Three fixed synthetic facts only; no UI live flag or arbitrary input selector."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.agents.operations_catalog import run

def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--source', required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--admission', type=Path)
    parser.add_argument('--gateway-config', type=Path)
    args = parser.parse_args()
    if args.live != bool(args.admission and args.gateway_config):
        raise ValueError
    def private(path):
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600 or info.st_size > 16384:
            raise ValueError
        return json.loads(path.read_text())
    receipt = run(state=args.state, source=args.source,
        admission=private(args.admission) if args.live else None,
        config=private(args.gateway_config) if args.live else None,
        acknowledgement=os.environ.get('PORTFOLIO_OPERATIONS_SYNTHETIC_ACK'))
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('operations_reasoning:blocked; no automatic replay') from None
