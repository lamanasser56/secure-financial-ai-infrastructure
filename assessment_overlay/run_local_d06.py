"""Run only the missing D06 step against a fresh local PostgreSQL engine."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BIN = Path('/home/lama/security-assessments/2026-10-22-independent-live/rc1-high-remediation/test-tools/pgserver/pginstall/bin')
SITE = Path('/home/lama/security-assessments/2026-10-22-independent-live/live-recovery-2026-10-24/container-roots/agent-platform-app/usr/local/lib/python3.12/site-packages')


def run():
    with tempfile.TemporaryDirectory(prefix='rc1-d06-') as temporary:
        data = Path(temporary) / 'data'
        subprocess.run([str(BIN / 'initdb'), '-D', str(data), '--auth=trust', '--auth-local=trust', '-U', 'postgres'],
                       check=True, capture_output=True, timeout=45)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, FINANCE_TEST_DSN=f'postgresql://postgres@127.0.0.1:{port}/postgres',
                   PYTHONPATH=os.pathsep.join((str(ROOT / 'platform/core/src'), str(ROOT / 'platform/core/tests'), str(SITE))),
                   PYTHONDONTWRITEBYTECODE='1')
        started = False
        try:
            subprocess.run([str(BIN / 'pg_ctl'), '-D', str(data), '-l', str(Path(temporary) / 'postgres.log'),
                            '-o', f'-h 127.0.0.1 -p {port}', '-w', 'start'],
                           check=True, capture_output=True, timeout=35)
            started = True
            result = subprocess.run([sys.executable, '-m', 'unittest',
                                     'test_finance_db.FinanceDatabase.test_reused_broker_connection_clears_scoped_identity', '-v'],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=70)
            if result.returncode:
                raise RuntimeError(result.stderr[-1600:])
            return {'engine': 'PostgreSQL 16.2 local native binary', 'result': 'PASS',
                    'case': 'same broker connection queries zero rows after scoped transaction',
                    'test_output': result.stderr[-600:]}
        finally:
            if started:
                subprocess.run([str(BIN / 'pg_ctl'), '-D', str(data), '-m', 'immediate', '-w', 'stop'],
                               check=True, capture_output=True, timeout=35)


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
