#!/usr/bin/env python3
"""Runnable local application using its freshly qualified nonroot database.

An isolated 2 GiB RAM Docker/containerd store avoids changing the standing worker
daemon or pruning retained work. Only the fixed qualified database archive loads.
The gateway/app use the locked worker interpreter; model/redaction remain simulated.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = '3c40f12dedf3aa18582db0bda6d4b6de8cb85c32994b718a8c0b78577f41454e'
CONFIG = 'sha256:58ee07cf0cd4256e3719d4e51e230d1d7c26369002cc2e65050881557abbaa0b'


class LocalApplicationBlocked(ValueError):
    """Only closed supervisor codes may enter the public launcher error."""
    def __init__(self, code):
        if code not in ('ORPHANED_LAUNCHER', 'STOP_TIMEOUT'):
            raise ValueError
        self.code = code
        super().__init__(code)


def interruption_signals():
    return (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def install_interrupt_handlers():
    def interrupted(*_):
        raise KeyboardInterrupt
    for name in interruption_signals():
        if name == signal.SIGHUP and signal.getsignal(name) == signal.SIG_IGN:
            # Preserve explicit nohup disposition for a detached operator run.
            continue
        signal.signal(name, interrupted)


def ignore_interrupt_handlers():
    # Repeated terminal hangups must not interrupt owned cleanup phases.
    for name in interruption_signals():
        signal.signal(name, signal.SIG_IGN)


def write_status(state, **value):
    path = state / 'launcher-status.json'
    path.write_text(json.dumps(value) + '\n')
    path.chmod(0o600)


def cleanup_steps(steps):
    """Attempt every owned cleanup phase even if an earlier phase fails."""
    failures = []
    for name, action in steps:
        try:
            action()
        except Exception:
            failures.append(name)
    return failures


def launcher_source(argv, cwd):
    for argument in argv[1:]:
        if argument in (b'-B', b'-u', b'-I', b'-E', b'-s'):
            continue
        if argument.endswith(b'run-qualified-local-agents.py'):
            return (cwd / os.fsdecode(argument)).resolve()
        break
    return None


def stop(state):
    info = state.lstat()
    path = state / 'launcher-owner.json'
    meta = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or not stat.S_ISREG(meta.st_mode)
            or meta.st_uid != os.getuid() or meta.st_nlink != 1
            or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_size > 2048):
        raise ValueError
    owner = json.loads(path.read_text())
    proc = Path('/proc') / str(owner['pid'])
    if proc.exists():
        fields = (proc / 'stat').read_text().split()
        if fields[21] != owner['start_ticks'] or owner['pid'] == os.getpid():
            raise ValueError
        argv = (proc / 'cmdline').read_bytes().split(b'\0')
        cwd = (proc / 'cwd').resolve()
        state_argument = ((cwd / os.fsdecode(argv[argv.index(b'--state') + 1])).resolve()
                          if b'--state' in argv else None)
        if (os.stat(proc).st_uid != os.getuid() or fields[2] == 'Z'
                or launcher_source(argv, cwd) != Path(__file__).resolve() or state_argument != state):
            raise ValueError
        os.kill(owner['pid'], signal.SIGTERM)
    until = time.monotonic() + 60
    while time.monotonic() < until:
        status = state / 'launcher-status.json'
        if status.exists() and json.loads(status.read_text()).get('cleanup_complete') is True:
            print(json.dumps({'owned_stack_stopped': True, 'private_audit_retained': True}))
            return
        if not proc.exists():
            # No unsafe port-owner kill or unverified orphan recovery.
            raise LocalApplicationBlocked('ORPHANED_LAUNCHER')
        time.sleep(.1)
    raise LocalApplicationBlocked('STOP_TIMEOUT')


def run(args):
    if args.state.exists() or args.state.parent.is_symlink():
        raise ValueError
    args.state.mkdir(mode=0o700)
    (args.state / 'launcher-owner.json').write_text(json.dumps({
        'pid': os.getpid(), 'start_ticks': Path('/proc/self/stat').read_text().split()[21]}) + '\n')
    (args.state / 'launcher-owner.json').chmod(0o600)
    ram = args.state / 'ram'
    ram.mkdir(mode=0o700)
    stack_state = args.state / 'application'
    log = (args.state / 'private-runtime.log').open('xb')
    mounted = False
    stage = 'PORT_PREFLIGHT'
    failure = None
    containerd = daemon = ui = None
    spec = importlib.util.spec_from_file_location('qualified_stack', ROOT / 'scripts/local-agent-stack.py')
    stack = importlib.util.module_from_spec(spec); spec.loader.exec_module(stack)
    docker = ['sudo', 'env', 'DOCKER_HOST=unix://' + str(ram / 'docker.sock'),
              'DOCKER_CONFIG=' + str(ram / 'docker-config'), 'docker']
    def checked(command, timeout=60):
        q = subprocess.run(command, stdout=log, stderr=log, timeout=timeout)
        if q.returncode:
            raise ValueError
    def ready(command, process):
        until = time.monotonic() + 30
        while time.monotonic() < until:
            if subprocess.run(command, stdout=log, stderr=log).returncode == 0:
                return
            if process.poll() is not None:
                raise ValueError
            time.sleep(.25)
        raise ValueError
    try:
        ports = (4001, 8767) if args.check or args.rehearse else (args.port, 4001, 8767)
        if not 1024 <= args.port <= 65535 or args.port in (8765, 4001, 8767):
            raise ValueError
        stack.require_free_ports(ports)
        stage = 'RAM_RUNTIME_START'
        checked(['sudo', 'mount', '-t', 'tmpfs', '-o', 'size=2G,mode=0700,uid=' + str(os.getuid()),
                 'portfolio-local-agents', str(ram)]); mounted = True
        (ram / 'containerd.toml').write_text('version = 3\n')
        containerd = subprocess.Popen(['sudo', '/usr/bin/containerd', '--config=' + str(ram / 'containerd.toml'),
            '--root=' + str(ram / 'containerd'), '--state=' + str(ram / 'containerd-state'),
            '--address=' + str(ram / 'containerd.sock')], stdout=log, stderr=log, start_new_session=True)
        ready(['sudo', 'ctr', '--address', str(ram / 'containerd.sock'), 'namespaces', 'list'], containerd)
        daemon = subprocess.Popen(['sudo', '/usr/bin/dockerd', '--containerd=' + str(ram / 'containerd.sock'),
            '--host=unix://' + str(ram / 'docker.sock'), '--data-root=' + str(ram / 'docker'),
            '--exec-root=' + str(ram / 'run'), '--pidfile=' + str(ram / 'docker.pid'), '--bridge=none',
            '--iptables=false', '--ip6tables=false', '--ip-forward=false', '--ip-masq=false',
            '--containerd-namespace=portfolio-local-qualified', '--containerd-plugins-namespace=portfolio-local-qualified-plugins'],
            stdout=log, stderr=log, start_new_session=True)
        ready(docker + ['info'], daemon)
        stage = 'QUALIFIED_DATABASE_LOAD'
        archive = ram / 'database.tar'
        digest = hashlib.sha256()
        if args.database_archive.is_symlink() or not args.database_archive.is_file():
            raise ValueError
        with gzip.open(args.database_archive, 'rb') as src, archive.open('xb') as dst:
            while chunk := src.read(1048576):
                digest.update(chunk); dst.write(chunk)
                if dst.tell() > 536870912:
                    raise ValueError
        if digest.hexdigest() != ARCHIVE_SHA:
            raise ValueError
        with tarfile.open(archive) as stream:
            manifest = json.load(stream.extractfile('manifest.json'))
            config = stream.extractfile(manifest[0]['Config']).read()
            if len(manifest) != 1 or 'sha256:' + hashlib.sha256(config).hexdigest() != CONFIG:
                raise ValueError
        checked(docker + ['load', '--input', str(archive)], timeout=120)
        archive.unlink()
        stack.DOCKER_COMMAND = docker
        stage = 'APPLICATION_STACK_START'
        stack.up(stack_state, args.python, 'portfolio-agent-database:qualified', qualified_nonroot=True)
        if args.check:
            checked([str(args.python), str(ROOT / 'scripts/check-local-agent-stack.py'), '--state', str(stack_state)], timeout=180)
        elif args.rehearse:
            checked([str(args.python), str(ROOT / 'scripts/rehearse-integrated-demo.py'), '--state', str(stack_state)], timeout=180)
        else:
            stage = 'UI_START'
            ui_log = (stack_state / 'ui.log').open('xb')
            ui = subprocess.Popen([str(args.python), str(ROOT / 'scripts/serve-integrated-agents.py'),
                '--state', str(stack_state), '--user', args.user, '--port', str(args.port)],
                stdout=ui_log, stderr=ui_log, start_new_session=True)
            ui_log.close()
            import urllib.request
            until = time.monotonic() + 10
            while time.monotonic() < until:
                if ui.poll() is not None:
                    raise ValueError
                try:
                    request = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with request.open('http://127.0.0.1:' + str(args.port), timeout=1) as response:
                        if response.status == 200:
                            stack.require_listener({'pid': ui.pid,
                                'start_ticks': Path('/proc/' + str(ui.pid) + '/stat').read_text().split()[21]}, args.port)
                            break
                except OSError:
                    pass
                time.sleep(.1)
            else:
                raise ValueError
            stage = 'RUNNING'
            write_status(args.state, stage=stage, cleanup_complete=False)
            print(json.dumps({'url': 'http://127.0.0.1:' + str(args.port), 'upstream': 'stub',
                              'redaction': 'simulated', 'live_enabled': False}), flush=True)
            if ui.wait() != 0:
                raise ValueError
    except Exception:
        failure = stage
        raise
    finally:
        ignore_interrupt_handlers()
        def stop_ui():
            if ui is not None and ui.poll() is None:
                os.killpg(ui.pid, signal.SIGTERM); ui.wait(timeout=10)
        def stop_stack():
            if (stack_state / 'operator.json').exists():
                stack.down(stack_state)
        def stop_daemon():
            if daemon is not None and daemon.poll() is None:
                checked(['sudo', 'kill', '-TERM', (ram / 'docker.pid').read_text().strip()])
                daemon.wait(timeout=30)
        def stop_containerd():
            if containerd is not None and containerd.poll() is None:
                checked(['sudo', 'kill', '-TERM', '--', '-' + str(containerd.pid)])
                containerd.wait(timeout=10)
        def unmount():
            if not mounted:
                return
            for point in sorted([l.split()[4] for l in Path('/proc/self/mountinfo').read_text().splitlines()
                                 if l.split()[4].startswith(str(ram) + '/')], key=len, reverse=True):
                checked(['sudo', 'umount', point])
            checked(['sudo', 'umount', str(ram)])
        failures = cleanup_steps([('ui', stop_ui), ('application', stop_stack),
                                  ('docker', stop_daemon), ('containerd', stop_containerd), ('ram', unmount)])
        log.close()
        write_status(args.state, stage='STOPPED', startup_failure_stage=failure,
                     cleanup_complete=not failures, cleanup_failures=failures)
        print(json.dumps({'owned_stack_stopped': not failures, 'ram_store_removed': not failures,
                          'private_audit_retained': True, 'original_daemon_changed': False}))
        if failures:
            raise ValueError


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--python', type=Path)
    parser.add_argument('--database-archive', type=Path)
    parser.add_argument('--user', choices=('alpha', 'beta'), default='alpha')
    parser.add_argument('--port', type=int, default=8768)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true')
    group.add_argument('--rehearse', action='store_true')
    group.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    args.state = args.state.absolute()
    if not args.stop and (args.python is None or args.database_archive is None):
        parser.error('--python and --database-archive are required when starting')
    install_interrupt_handlers()
    try:
        stop(args.state) if args.stop else run(args)
    except KeyboardInterrupt:
        pass
    except Exception as failure:
        stage = '; stage=' + failure.code if isinstance(failure, LocalApplicationBlocked) else ''
        raise SystemExit('local_application:blocked' + stage + '; private evidence retained') from None
