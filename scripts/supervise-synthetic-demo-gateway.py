#!/usr/bin/env python3
"""Prepared once-only gateway process with database/log/deadline quarantine.

Separately hashed operator program, never selected by the local UI. Child output
stays in a bounded private tmpfs file and is not copied into retained evidence.
No restart, key issuance, model probe or retry occurs in this supervisor.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


# The image is distroless: prisma's platform probe shells out to `cat` and `openssl`, which do not exist, so the
# query engine never starts. The engine binary is already fixed by PRISMA_QUERY_ENGINE_BINARY, and the schema is
# applied by bootstrap-database, so LiteLLM's Prisma CLI path (schema diff/migrations, which downloads Node.js) is
# not needed. Both replacements are reviewed for these exact package versions only; any drift refuses to start.
REVIEWED_TOOLCHAIN = {'litellm': '1.104.0', 'prisma': '0.15.0'}
PRISMA_BINARY_PLATFORM = 'debian-openssl-3.0.x'
PROXY_PRELUDE = f"""import sys
from importlib.metadata import version
for _name, _expected in {sorted(REVIEWED_TOOLCHAIN.items())!r}:
    if version(_name) != _expected:
        raise SystemExit('gateway:toolchain_unreviewed:' + _name)
import prisma.binaries.platform as prisma_platform
prisma_platform.binary_platform = lambda: {PRISMA_BINARY_PLATFORM!r}
import litellm_proxy_extras.prisma_toolchain as prisma_toolchain
prisma_toolchain.prisma_cli_available = lambda: False
sys.argv = ['/app/proxy.py', *sys.argv[1:]]
from litellm.proxy.proxy_cli import run_server
run_server()
"""


class ToolchainUnreviewed(Exception):
    pass


def require_reviewed_toolchain(version=None):
    if version is None:
        from importlib.metadata import version
    found = {name: version(name) for name in REVIEWED_TOOLCHAIN}
    if found != REVIEWED_TOOLCHAIN:
        raise ToolchainUnreviewed


def run():
    require_reviewed_toolchain()  # before the once-only start marker: drift has no side effect
    import psycopg
    state = Path('/state')
    fd = os.open(state / 'gateway-started', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    # These secrets belong only to this gateway process, never to the app.
    config = json.loads(Path('/admission/gateway.json').read_text())
    if set(config) != {'master_key', 'salt_key', 'database_url', 'project_id', 'expires_at'}:
        raise ValueError
    if not time.time() < config['expires_at'] <= time.time() + 900:
        raise ValueError
    environment = dict(os.environ, LITELLM_MASTER_KEY=config['master_key'],
                       LITELLM_SALT_KEY=config['salt_key'], DATABASE_URL=config['database_url'],
                       PORTFOLIO_VERTEX_PROJECT=config['project_id'])
    log_path = state / 'private-gateway.log'
    with log_path.open('xb') as log:
        child = subprocess.Popen(['/usr/local/bin/python3.12', '-c', PROXY_PRELUDE,
            '--config', '/configuration/litellm-vertex.yaml', '--host', '0.0.0.0', '--port', '4000'],
            env=environment, stdout=log, stderr=log, start_new_session=True)
        stop = [False]
        signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__(0, True))
        reason = 'CHILD_EXIT'
        try:
            while child.poll() is None:
                if stop[0] or time.time() >= config['expires_at']:
                    reason = 'STOP_OR_DEADLINE'; break
                if log_path.stat().st_size > 8 * 1024 * 1024:
                    reason = 'PRIVATE_LOG_LIMIT'; break
                try:
                    with psycopg.connect(config['database_url'], connect_timeout=1,
                                         options='-c statement_timeout=1000') as db:
                        if db.execute('SELECT 1').fetchone() != (1,):
                            raise ValueError
                except Exception:
                    reason = 'DATABASE_UNAVAILABLE'; break
                time.sleep(1)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=5)
    print(json.dumps({'gateway_stopped': True, 'reason': reason, 'restarts': 0,
                      'automatic_replay': False, 'raw_log_retained': False}))
    if reason not in {'STOP_OR_DEADLINE'}:
        raise SystemExit(1)


if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) != 1:
        raise SystemExit('gateway:arguments_rejected')
    try:
        run()
    except ToolchainUnreviewed:
        print('{"status":"BLOCKED","code":"GATEWAY_TOOLCHAIN_UNREVIEWED","automatic_retry":false}')
        raise SystemExit(1) from None
    except Exception:
        print('{"status":"BLOCKED","code":"GATEWAY_SUPERVISION_FAILURE","automatic_retry":false}')
        raise SystemExit(1) from None
