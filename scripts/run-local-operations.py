#!/usr/bin/env python3
"""Separate bounded loopback Security & Operations UI; existing demos preserved."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.agents.operations import OperationsAudit, OperationsController, private_directory
from runtime.agents.operations_local import ProcVisibility, fixture_identity, register_monitor, registered_targets, sandbox_targets, stop_sandbox_child
from runtime.agents.operations_model import OperationsExplainer
from runtime.agents.operations_service import OperationsService
from runtime.agents.web import DemoServer


def private_json(path):
    info = path.lstat()
    if path.is_symlink() or not path.is_file() or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600 or info.st_size > 32768:
        raise ValueError
    return json.loads(path.read_text())


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8769)
    parser.add_argument('--sandbox', action='store_true')
    parser.add_argument('--monitor-demo-state', type=Path)
    parser.add_argument('--security-config', type=Path)
    parser.add_argument('--model-config', type=Path)
    parser.add_argument('--registry-config', type=Path)
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    state = args.state.absolute()
    if args.stop:
        private_directory(state)
        owner = private_json(state / 'owner.json')
        from runtime.agents.operations import process_identity
        current = process_identity(owner['pid'])
        if current is None:
            if not (state / 'stopped.json').exists():
                raise ValueError
            if not private_json(state / 'stopped.json')['cleanup_complete']:
                raise ValueError
            print(json.dumps({'server_stopped': True, 'audit_retained': True})); return
        if current != owner or current['pid'] == os.getpid():
            raise ValueError
        os.kill(owner['pid'], signal.SIGTERM)
        until = time.monotonic() + 10
        while time.monotonic() < until:
            if (state / 'stopped.json').exists() and process_identity(owner['pid']) is None:
                if not private_json(state / 'stopped.json')['cleanup_complete']:
                    raise ValueError
                print(json.dumps({'server_stopped': True, 'audit_retained': True})); return
            time.sleep(.1)
        raise ValueError
    if args.port in (8765, 8768, 8767, 4001) or not 1024 <= args.port <= 65535 or state.exists():
        raise ValueError
    state.mkdir(mode=0o700)
    from runtime.agents.operations import process_identity
    (state / 'owner.json').write_text(json.dumps(process_identity(os.getpid())) + '\n')
    approval_secret = secrets.token_urlsafe(32)
    (state / 'operator-approval.secret').write_text(approval_secret + '\n')
    identity, authorization, tenant = fixture_identity()
    targets, child, member = {}, None, None
    audit_path = state / 'audit'; audit_path.mkdir(mode=0o700)
    audit = OperationsAudit(audit_path)
    try:
        if args.sandbox:
            targets, child = sandbox_targets(state, tenant)
            member = targets['sandbox-demo'].members[0]
        if args.monitor_demo_state:
            targets['current-demo'] = register_monitor(args.monitor_demo_state, tenant)
        if args.registry_config:
            registered = registered_targets(private_json(args.registry_config), tenant)
            if set(registered) & set(targets):
                raise ValueError
            targets.update(registered)
        model = None
        if args.model_config:
            try:
                model = OperationsExplainer(private_json(args.model_config))
            except Exception:
                # Invalid/expired model admission cannot take monitoring offline.
                (state / 'model-admission.json').write_text(json.dumps({'code': 'MODEL_CLIENT_ADMISSION_BLOCKED'}) + '\n')
        controller = OperationsController(audit, identity, authorization, targets,
            approval_secret=approval_secret, visibility=ProcVisibility(), model=model)
        service = OperationsService(controller,
            private_json(args.security_config) if args.security_config else None)
        def interrupted(*_):
            raise KeyboardInterrupt
        for name in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            if name == signal.SIGHUP and signal.getsignal(name) == signal.SIG_IGN:
                continue
            signal.signal(name, interrupted)
        with DemoServer(('127.0.0.1', args.port), operations=service) as server:
            print(json.dumps({'operations_url': server.origin + '/operations.html',
                'live_enabled': False, 'monitoring': 'actual_local',
                'model_mode': controller.budgets()['model_mode']}), flush=True)
            server.serve_forever()
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        failures = []
        try:
            if child is not None:
                stop_sandbox_child(child, member)
        except Exception:
            failures.append('OWNED_SANDBOX_STOP_FAILED')
        try:
            audit.close()
        except Exception:
            failures.append('AUDIT_CLOSE_FAILED')
        receipt = {'server_stopped': True, 'audit_retained': True,
                   'cleanup_complete': not failures, 'failures': failures}
        (state / 'stopped.json').write_text(json.dumps(receipt) + '\n')
        if failures:
            raise ValueError


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit('operations:blocked; inspect private state') from None
