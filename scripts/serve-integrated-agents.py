#!/usr/bin/env python3
"""Separate loopback application: actual local proxy/DB, simulated boundaries."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.agents.audit_preparation import DurableToolAudit
from runtime.agents.composition import compose_local
from runtime.agents.terminal_audit import TerminalAudit
from runtime.agents.web import DemoServer


def private_json(path):
    info = path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > 32768):
        raise ValueError("composition:private_configuration_required")
    return json.loads(path.read_text())


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--user", choices=("alpha", "beta"), default="alpha")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    import psycopg
    config = private_json(args.state / ("application-" + args.user + ".json"))
    tools = DurableToolAudit(args.state / ("audit-tools-" + args.user))
    terminal = TerminalAudit(args.state / ("audit-turns-" + args.user))
    try:
        agents, _, _ = compose_local(config,
            connect=lambda: psycopg.connect(config["tenant_database_url"], connect_timeout=2),
            terminal_sink=terminal, tool_sink=tools)
        with DemoServer(("127.0.0.1", args.port), agents=agents,
                        composition="local_proxy_stub") as server:
            print("Local integration UI: " + server.origin
                  + "; real LiteLLM/PostgreSQL, fixture identity, simulated model/redaction, live disabled",
                  flush=True)
            server.serve_forever()
    finally:
        tools.close()
        terminal.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        print("composition:startup_or_runtime_blocked", file=sys.stderr)
        raise SystemExit(1) from None
