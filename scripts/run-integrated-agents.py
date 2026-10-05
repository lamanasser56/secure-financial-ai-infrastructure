#!/usr/bin/env python3
"""Start the local integrated UI and remove only its owned stack on exit."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--postgres-image", required=True)
    parser.add_argument("--user", choices=("alpha", "beta"), default="alpha")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("stack", ROOT / "scripts/local-agent-stack.py")
    stack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stack)
    if args.state.exists():
        raise ValueError("composition:new_private_state_required")
    process = None
    try:
        subprocess.run([str(args.python), str(ROOT / "scripts/local-agent-stack.py"), "up",
                        "--state", str(args.state), "--python", str(args.python),
                        "--postgres-image", args.postgres_image], check=True)
        process = subprocess.Popen([str(args.python), str(ROOT / "scripts/serve-integrated-agents.py"),
                                    "--state", str(args.state), "--user", args.user,
                                    "--port", str(args.port)], cwd=ROOT)
        process.wait()
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        if (args.state / "operator.json").exists():
            stack.down(args.state)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        print("composition:blocked; no automatic restart", file=sys.stderr)
        raise SystemExit(1) from None
