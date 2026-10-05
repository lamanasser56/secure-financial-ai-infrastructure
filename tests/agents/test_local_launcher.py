"""Linux local-launch regressions: real sockets/children, no provider calls."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import signal
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(process):
    return {'pid': process.pid, 'start_ticks': Path('/proc/' + str(process.pid) + '/stat').read_text().split()[21]}


class LauncherTests(unittest.TestCase):
    def test_relative_launcher_path_is_resolved_but_command_text_is_not(self):
        launcher = load('run-qualified-local-agents')
        expected = ROOT / 'scripts/run-qualified-local-agents.py'
        self.assertEqual(launcher.launcher_source([b'python', b'scripts/run-qualified-local-agents.py'], ROOT), expected)
        self.assertEqual(launcher.launcher_source([b'python', b'-B', str(expected).encode()], Path('/tmp')), expected)
        self.assertIsNone(launcher.launcher_source([b'python', b'-c', b'pass', str(expected).encode()], ROOT))

    def test_occupied_port_blocks_before_database_or_credentials(self):
        stack = load('local-agent-stack')
        with socket.socket() as listener, tempfile.TemporaryDirectory() as directory:
            listener.bind(('127.0.0.1', 0)); listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaisesRegex(ValueError, 'port_in_use'):
                stack.require_free_ports((port,))
            with mock.patch.object(stack, 'require_free_ports', side_effect=ValueError), \
                    mock.patch.object(stack, 'command') as docker:
                state = Path(directory) / 'application'
                with self.assertRaises(ValueError):
                    stack.up(state, Path(sys.executable), 'unused')
                self.assertFalse(state.exists())
                docker.assert_not_called()

    def test_listener_must_belong_to_recorded_child(self):
        stack = load('local-agent-stack')
        program = "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1],flush=True); time.sleep(20)"
        child = subprocess.Popen([sys.executable, '-c', program, str(ROOT)], stdout=subprocess.PIPE, text=True, start_new_session=True)
        try:
            port = int(child.stdout.readline())
            stack.require_listener(record(child), port)
            own = {'pid': os.getpid(), 'start_ticks': Path('/proc/self/stat').read_text().split()[21]}
            with self.assertRaisesRegex(ValueError, 'listener_not_owned'):
                stack.require_listener(own, port)
            stack.stop_process(record(child))
            self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None: child.terminate()
            child.wait(timeout=5); child.stdout.close()

    def test_exited_zombie_is_not_an_unowned_live_process(self):
        stack = load('local-agent-stack')
        child = subprocess.Popen([sys.executable, '-c', 'pass'], start_new_session=True)
        try:
            identity = record(child)
            until = time.monotonic() + 5
            while Path('/proc/' + str(child.pid) + '/stat').read_text().split()[2] != 'Z':
                self.assertLess(time.monotonic(), until); time.sleep(.01)
            with self.assertRaisesRegex(ValueError, 'service_exited'):
                stack.require_running([identity])
            with mock.patch.object(os, 'killpg') as kill:
                stack.stop_process(identity)
                kill.assert_not_called()
        finally:
            child.wait(timeout=5)

    def test_pid_identity_change_blocks_signal(self):
        stack = load('local-agent-stack')
        child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)', str(ROOT)], start_new_session=True)
        try:
            identity = record(child) | {'start_ticks': 'wrong'}
            with mock.patch.object(os, 'killpg') as kill:
                with self.assertRaisesRegex(ValueError, 'process_changed'):
                    stack.stop_process(identity)
                kill.assert_not_called()
        finally:
            child.terminate(); child.wait(timeout=5)

    def test_cleanup_failure_does_not_skip_later_owned_phases(self):
        launcher = load('run-qualified-local-agents')
        actions = []
        def failed():
            actions.append('application'); raise ValueError
        failures = launcher.cleanup_steps([('application', failed),
            ('docker', lambda: actions.append('docker')), ('ram', lambda: actions.append('ram'))])
        self.assertEqual(failures, ['application'])
        self.assertEqual(actions, ['application', 'docker', 'ram'])

    def test_stop_rejects_an_unrelated_process_without_signalling(self):
        launcher = load('run-qualified-local-agents')
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory); state.chmod(0o700)
            child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)'])
            try:
                path = state / 'launcher-owner.json'
                path.write_text(json.dumps(record(child))); path.chmod(0o600)
                with mock.patch.object(os, 'kill') as kill:
                    with self.assertRaises(ValueError): launcher.stop(state)
                    kill.assert_not_called()
            finally:
                child.terminate(); child.wait(timeout=5)

    def test_closed_status_contains_no_exception_or_configuration(self):
        launcher = load('run-qualified-local-agents')
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            launcher.write_status(state, stage='STOPPED', startup_failure_stage='PORT_PREFLIGHT',
                                  cleanup_complete=True, cleanup_failures=[])
            status = json.loads((state / 'launcher-status.json').read_text())
            self.assertEqual(set(status), {'stage', 'startup_failure_stage', 'cleanup_complete', 'cleanup_failures'})
            self.assertEqual((state / 'launcher-status.json').stat().st_mode & 0o777, 0o600)

    def test_absent_supervisor_has_finite_reason_without_signalling_children(self):
        launcher = load('run-qualified-local-agents')
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory); state.chmod(0o700)
            child = subprocess.Popen([sys.executable, '-c', 'pass'])
            identity = record(child); child.wait(timeout=5)
            path = state / 'launcher-owner.json'
            path.write_text(json.dumps(identity)); path.chmod(0o600)
            launcher.write_status(state, stage='RUNNING', cleanup_complete=False)
            with mock.patch.object(os, 'kill') as kill:
                with self.assertRaises(launcher.LocalApplicationBlocked) as caught:
                    launcher.stop(state)
                self.assertEqual(caught.exception.code, 'ORPHANED_LAUNCHER')
                kill.assert_not_called()

    def test_verified_recovered_status_allows_idempotent_stop(self):
        launcher = load('run-qualified-local-agents')
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory); state.chmod(0o700)
            child = subprocess.Popen([sys.executable, '-c', 'pass'])
            identity = record(child); child.wait(timeout=5)
            path = state / 'launcher-owner.json'
            path.write_text(json.dumps(identity)); path.chmod(0o600)
            launcher.write_status(state, stage='STOPPED', cleanup_complete=True)
            with mock.patch.object(os, 'kill') as kill:
                launcher.stop(state)
                kill.assert_not_called()

    def test_hangup_runs_cleanup_and_repeated_hangup_does_not_interrupt_it(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'closed'
            # Real signal/child behavior; no Docker, model or provider double.
            program = (
                "import importlib.util,time,pathlib,signal; signal.signal(signal.SIGHUP,signal.SIG_DFL); "
                "s=importlib.util.spec_from_file_location('launcher',%r); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "m.install_interrupt_handlers()\n"
                "try:\n print('ready',flush=True); time.sleep(20)\n"
                "except KeyboardInterrupt:\n pass\n"
                "finally:\n m.ignore_interrupt_handlers(); print('cleaning',flush=True); "
                "time.sleep(.2); pathlib.Path(%r).write_text('owned cleanup complete')\n"
            ) % (str(ROOT / 'scripts/run-qualified-local-agents.py'), str(marker))
            child = subprocess.Popen([sys.executable, '-c', program], stdout=subprocess.PIPE,
                                     text=True, start_new_session=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                os.kill(child.pid, signal.SIGHUP)
                self.assertEqual(child.stdout.readline().strip(), 'cleaning')
                os.kill(child.pid, signal.SIGHUP)
                self.assertEqual(child.wait(timeout=5), 0)
                self.assertEqual(marker.read_text(), 'owned cleanup complete')
            finally:
                if child.poll() is None: child.terminate()
                child.wait(timeout=5); child.stdout.close()

    def test_explicit_nohup_disposition_survives_hangup_and_term_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'closed'
            program = (
                "import importlib.util,time,pathlib,signal; signal.signal(signal.SIGHUP,signal.SIG_IGN); "
                "s=importlib.util.spec_from_file_location('launcher',%r); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "m.install_interrupt_handlers()\n"
                "try:\n print('ready',flush=True); time.sleep(20)\n"
                "except KeyboardInterrupt:\n pass\n"
                "finally:\n m.ignore_interrupt_handlers(); pathlib.Path(%r).write_text('closed')\n"
            ) % (str(ROOT / 'scripts/run-qualified-local-agents.py'), str(marker))
            child = subprocess.Popen([sys.executable, '-c', program], stdout=subprocess.PIPE,
                                     text=True, start_new_session=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                os.kill(child.pid, signal.SIGHUP); time.sleep(.1)
                self.assertIsNone(child.poll())
                os.kill(child.pid, signal.SIGTERM)
                self.assertEqual(child.wait(timeout=5), 0)
                self.assertEqual(marker.read_text(), 'closed')
            finally:
                if child.poll() is None: child.terminate()
                child.wait(timeout=5); child.stdout.close()
