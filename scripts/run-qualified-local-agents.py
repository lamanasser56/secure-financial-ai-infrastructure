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
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = '3c40f12dedf3aa18582db0bda6d4b6de8cb85c32994b718a8c0b78577f41454e'
CONFIG = 'sha256:58ee07cf0cd4256e3719d4e51e230d1d7c26369002cc2e65050881557abbaa0b'


def run(args):
    if args.state.exists() or args.state.parent.is_symlink():
        raise ValueError
    args.state.mkdir(mode=0o700)
    ram = args.state / 'ram'
    ram.mkdir(mode=0o700)
    stack_state = args.state / 'application'
    log = (args.state / 'private-runtime.log').open('xb')
    mounted = False
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
        stack.up(stack_state, args.python, 'portfolio-agent-database:qualified', qualified_nonroot=True)
        if args.check:
            checked([str(args.python), str(ROOT / 'scripts/check-local-agent-stack.py'), '--state', str(stack_state)], timeout=180)
        elif args.rehearse:
            checked([str(args.python), str(ROOT / 'scripts/rehearse-integrated-demo.py'), '--state', str(stack_state)], timeout=180)
        else:
            ui = subprocess.Popen([str(args.python), str(ROOT / 'scripts/serve-integrated-agents.py'),
                '--state', str(stack_state), '--user', args.user, '--port', str(args.port)], start_new_session=True)
            print(json.dumps({'url': 'http://127.0.0.1:' + str(args.port), 'upstream': 'stub',
                              'redaction': 'simulated', 'live_enabled': False}), flush=True)
            ui.wait()
    finally:
        if ui is not None and ui.poll() is None:
            os.killpg(ui.pid, signal.SIGTERM); ui.wait(timeout=10)
        if (stack_state / 'operator.json').exists():
            stack.down(stack_state)
        if daemon is not None and daemon.poll() is None:
            checked(['sudo', 'kill', '-TERM', (ram / 'docker.pid').read_text().strip()])
            daemon.wait(timeout=30)
        if containerd is not None and containerd.poll() is None:
            checked(['sudo', 'kill', '-TERM', '--', '-' + str(containerd.pid)])
            containerd.wait(timeout=10)
        if mounted:
            for point in sorted([l.split()[4] for l in Path('/proc/self/mountinfo').read_text().splitlines()
                                 if l.split()[4].startswith(str(ram) + '/')], key=len, reverse=True):
                checked(['sudo', 'umount', point])
            checked(['sudo', 'umount', str(ram)])
        log.close()
        print(json.dumps({'owned_stack_stopped': True, 'ram_store_removed': True,
                          'private_audit_retained': True, 'original_daemon_changed': False}))


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--database-archive', type=Path, required=True)
    parser.add_argument('--user', choices=('alpha', 'beta'), default='alpha')
    parser.add_argument('--port', type=int, default=8768)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true')
    group.add_argument('--rehearse', action='store_true')
    args = parser.parse_args()
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        run(args)
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit('local_application:blocked; private evidence retained') from None
