"""Runtime smoke harness: exact manifest commands, every declared workload, and failure on crash, hang or bad import."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('runtime_smoke', ROOT / 'scripts/runtime-smoke.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
KUBECTL = str(ROOT / '.cache/envtest-v1.35.0/kubectl')
IMAGES = {name: 'local/' + name + ':test' for name in smoke.LOCK_KEYS.values()}


class Result:
    def __init__(self, stdout='', returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, '', returncode


class FakeDocker:
    """Records docker invocations; container states come from `states` (id -> list of (status, exit, restarts))."""

    def __init__(self, states=None, sweep_missing=None):
        self.calls, self.states, self.sweep_missing, self.seen = [], states or {}, sweep_missing or {}, {}

    def __call__(self, *args, check=True, capture=True):
        self.calls.append(args)
        if args[0] == 'inspect':
            sequence = self.states.get(args[1], [('running', 0, 0)])
            index = self.seen.get(args[1], 0)
            self.seen[args[1]] = index + 1
            status, code, restarts = sequence[min(index, len(sequence) - 1)]
            return Result(json.dumps([{'State': {'Status': status, 'ExitCode': code}, 'RestartCount': restarts,
                                       'NetworkSettings': {'Networks': {'n': {'IPAddress': '10.0.0.2'}}}}]))
        if args[:2] == ('image', 'inspect'):
            return Result(json.dumps(['/usr/local/bin/python3.12', '-m', 'entry']))
        if args[0] == 'run' and '/sweep/image-import-sweep.py' in args:
            image = args[args.index('-B') - 1]
            missing = self.sweep_missing.get(image, [])
            return Result(json.dumps({'missing': missing, 'optional_missing': []}))
        return Result()


class Translation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs, cls.by_digest = smoke.render_workloads(KUBECTL)
        cls.secrets = smoke.synthetic_secrets()

    def workloads(self):
        return smoke.workloads_for(self.docs, self.by_digest, IMAGES, Path(tempfile.mkdtemp()), self.secrets)

    def test_every_declared_container_of_the_seven_images_is_run(self):
        expected = sum(len(d['spec']['template']['spec']['containers']) for d in self.docs
                       if d['kind'] in ('Deployment', 'StatefulSet', 'Job'))
        workloads = self.workloads()
        self.assertEqual(len(workloads), expected)
        self.assertEqual({w.image for w in workloads}, set(IMAGES.values()))
        self.assertIn('smoke-apps-fault-demo', {w.id for w in workloads})  # replicas 0 still runs its program

    def test_kubernetes_command_and_args_semantics_and_security_context(self):
        fake = FakeDocker()
        with patch.object(smoke, 'docker', fake):
            for w in self.workloads():
                w.start('net')
                run = fake.calls[-1]
                tail = list(run[run.index(w.image) + 1:])
                command, args = w.container.get('command'), w.container.get('args')
                if command:
                    self.assertEqual(run[run.index('--entrypoint') + 1], command[0])
                    self.assertEqual(tail, command[1:] + (args or []))
                else:
                    self.assertNotIn('--entrypoint', run)
                    self.assertEqual(tail, list(args or []))
                own = w.container.get('securityContext', {})
                if own.get('readOnlyRootFilesystem'):
                    self.assertIn('--read-only', run)
                if 'ALL' in own.get('capabilities', {}).get('drop', []):
                    self.assertIn('--cap-drop', run)
        by_id = {w.id: w for w in self.workloads()}
        self.assertEqual(by_id['smoke-platform-schema'].container['command'][-2:],
                         ['agent_platform.programs.bootstrap', 'all'])

    def test_service_names_resolve_to_the_selected_workloads(self):
        fake = FakeDocker()
        with patch.object(smoke, 'docker', fake):
            aliases = {}
            for w in self.workloads():
                w.start('net')
                run = fake.calls[-1]
                aliases[w.id] = {run[i + 1] for i, o in enumerate(run) if o == '--network-alias'}
        self.assertIn('postgres.platform.svc.cluster.local', aliases['smoke-platform-postgres'])
        self.assertIn('gateway-provider.platform.svc.cluster.local', aliases['smoke-platform-gateway'])
        self.assertIn('gateway.platform.svc.cluster.local', aliases['smoke-platform-gateway-boundary'])
        self.assertIn('redactor.platform.svc.cluster.local', aliases['smoke-platform-redactor'])

    def test_secrets_are_synthetic_and_complete_for_every_reference(self):
        fake = FakeDocker()
        with patch.object(smoke, 'docker', fake):
            for w in self.workloads():
                w.start('net')  # raises on any missing Secret/ConfigMap reference
        gateway = self.secrets[('platform', 'gateway')]
        self.assertTrue(gateway['master_key'].startswith('sk-'))


class Outcome(unittest.TestCase):
    def run_with(self, fake, *, probe=True):
        out = Path(tempfile.mkdtemp()) / 'report.json'
        with patch.object(smoke, 'docker', fake), patch.object(smoke, 'READY_SECONDS', 0.3), \
                patch.object(smoke, 'STABLE_SECONDS', 0.2), patch.object(smoke, 'PERIOD', 0.05), \
                patch.object(smoke.Workload, 'probe_ok', lambda self: probe), patch('builtins.print'):
            passed = smoke.run(IMAGES, KUBECTL, out)
        return passed, json.loads(out.read_text())

    def test_all_ready_and_job_completed_passes(self):
        passed, report = self.run_with(FakeDocker({'smoke-platform-schema': [('exited', 0, 0)]}))
        self.assertTrue(passed, report)
        self.assertEqual(report['workloads']['smoke-platform-schema']['status'], 'completed')
        self.assertEqual(report['workloads']['smoke-platform-gateway']['status'], 'stable')

    def test_crash_loop_after_ready_fails(self):
        states = {'smoke-platform-schema': [('exited', 0, 0)],
                  'smoke-platform-gateway': [('running', 0, 0), ('running', 0, 0), ('running', 0, 1)]}
        passed, report = self.run_with(FakeDocker(states))
        self.assertFalse(passed)
        self.assertEqual(report['workloads']['smoke-platform-gateway']['status'], 'unstable')

    def test_never_ready_and_failed_job_fail(self):
        passed, report = self.run_with(FakeDocker({'smoke-platform-schema': [('restarting', 1, 3)]}), probe=False)
        self.assertFalse(passed)
        self.assertEqual(report['workloads']['smoke-platform-schema']['status'], 'not_ready')
        self.assertEqual(report['workloads']['smoke-apps-app']['status'], 'not_ready')

    def test_missing_import_fails_even_when_everything_runs(self):
        fake = FakeDocker({'smoke-platform-schema': [('exited', 0, 0)]},
                          sweep_missing={IMAGES['agent-platform-app']: [{'module': 'google.auth', 'imported_by': 'x',
                                                                         'line': 1}]})
        passed, report = self.run_with(fake)
        self.assertFalse(passed)
        self.assertEqual(report['import_sweep']['agent-platform-app']['missing'][0]['module'], 'google.auth')

    def test_cleanup_removes_every_container_and_the_network(self):
        fake = FakeDocker({'smoke-platform-schema': [('exited', 0, 0)]})
        self.run_with(fake)
        removed = {c[2] for c in fake.calls if c[:2] == ('rm', '-f')}
        started = {c[c.index('--name') + 1] for c in fake.calls if c[0] == 'run' and '--name' in c}
        self.assertEqual(removed, started)
        self.assertTrue(any(c[:2] == ('network', 'rm') for c in fake.calls))


class ImportSweep(unittest.TestCase):
    def sweep(self, files, *entries):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in files.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(textwrap.dedent(text))
            result = subprocess.run([sys.executable, '-I', '-c',
                                     'import runpy,sys; sys.path.insert(0, sys.argv[1]); sys.argv = sys.argv[2:]; '
                                     'runpy.run_path(sys.argv[0], run_name="__main__")',
                                     str(root), str(ROOT / 'scripts/image-import-sweep.py'), *entries],
                                    capture_output=True, text=True, cwd=root)
            return result.returncode, json.loads(result.stdout)

    def test_lazy_missing_import_is_found_through_local_modules(self):
        code, result = self.sweep({'pkg/__init__.py': '', 'pkg/entry.py': 'from . import helper\n',
                                   'pkg/helper.py': 'def f():\n    from absent_vendor.auth import jwt\n'}, 'pkg.entry')
        self.assertEqual(code, 1)
        self.assertEqual([m['module'] for m in result['missing']], ['absent_vendor.auth'])

    def test_guarded_imports_attributes_and_stdlib_are_not_failures(self):
        code, result = self.sweep({'app.py': '''
            import json, os.path
            from pkg.helper import some_function
            try:
                import optional_vendor
            except ImportError:
                optional_vendor = None
            ''', 'pkg/__init__.py': '', 'pkg/helper.py': 'def some_function():\n    return 1\n'}, 'app')
        self.assertEqual(code, 0, result)
        self.assertEqual([m['module'] for m in result['optional_missing']], ['optional_vendor'])

    def test_missing_entry_module_fails(self):
        code, result = self.sweep({'app.py': ''}, 'not_there')
        self.assertEqual(code, 1)
        self.assertEqual(result['missing'][0]['imported_by'], '<entry>')


if __name__ == '__main__':
    unittest.main()
