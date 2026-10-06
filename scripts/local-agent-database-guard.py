#!/usr/bin/env python3
"""Owned local proxy quarantine on database loss; never restart or retry work."""
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import fcntl

ROOT = Path(__file__).resolve().parents[1]


def run(state):
    import psycopg
    config_path = state / "application-alpha.json"
    metadata = config_path.lstat()
    if (not config_path.is_file() or config_path.is_symlink()
            or metadata.st_uid != os.getuid() or metadata.st_nlink != 1
            or metadata.st_mode & 0o777 != 0o600):
        raise ValueError("database_guard:private_configuration_required")
    config = json.loads(config_path.read_text())
    records = json.loads((state / "processes.json").read_text())
    gateway = [record for record in records if record["name"] == "gateway"]
    if len(gateway) != 1:
        raise ValueError("database_guard:owned_proxy_required")
    spec = importlib.util.spec_from_file_location("stack", ROOT / "scripts/local-agent-stack.py")
    stack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stack)

    async def healthy():
        connection = None
        try:
            connection = await psycopg.AsyncConnection.connect(
                config["tenant_database_url"], connect_timeout=1,
                options="-c statement_timeout=1000", autocommit=True)
            cursor = await connection.execute("SELECT 1")
            if await cursor.fetchone() != (1,):
                raise ValueError
        finally:
            if connection is not None:
                await connection.close()

    while True:
        try:
            # Nonowner tenant-read credentials only. No migration, credential
            # refresh, request replay, provider call or probe containing data.
            asyncio.run(asyncio.wait_for(healthy(), timeout=2))
        except Exception:
            # Restoration updates the one owned service record while holding the
            # same lock. Quarantine must select that current process, never an old
            # PID or an arbitrary listener. No automatic restart is authorized.
            sys.path.insert(0, str(ROOT))
            from runtime.agents.service_restoration import service_lock, private_file
            with service_lock(state) as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                records = json.loads(private_file(state/'processes.json'))
                gateway = [record for record in records if record['name']=='gateway']
                if len(gateway)!=1:
                    raise ValueError('database_guard:owned_proxy_required')
                stack.write(state / 'database-quarantined.json', {
                    'code': 'DATABASE_UNAVAILABLE_PROXY_QUARANTINED',
                    'automatic_restart': False, 'automatic_request_replay': False})
                stack.stop_process(gateway[0])
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                path = Path(f"/proc/{gateway[0]['pid']}/stat")
                if not path.exists() or path.read_text().split()[2] == "Z":
                    break
                time.sleep(0.05)
            else:
                # Only the same verified owned process group can be killed.
                path = Path(f"/proc/{gateway[0]['pid']}/stat")
                if path.read_text().split()[21] != gateway[0]["start_ticks"]:
                    raise ValueError("database_guard:process_changed")
                import signal
                os.killpg(gateway[0]["pid"], signal.SIGKILL)
            return
        time.sleep(1)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.state)
    except Exception:
        print("database_guard:blocked", file=sys.stderr)
        raise SystemExit(1) from None
