"""Gateway startup in the distroless image: Prisma platform pin, no Prisma CLI path, reviewed versions only."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# Bundle of ad966add with only the gateway program, its annotation, its memory request and the staging init
# program (changed separately for fsGroup setgid) masked.
NORMALIZED_BUNDLE_SHA256 = 'c10b14203400fa441de802b2a18eb0d9d4dc4d20f6ec620ea5aefdf8ba1a9c10'


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def bundle():
    render = load('render-synthetic-demo-bundle')
    prefix = 'us-east1-docker.pkg.dev/project-fixture/sdp-evaluation-images/agent-demo-'
    return render.bundle('project-fixture', *[prefix + n + '@sha256:' + 'a' * 64 for n in ('gateway', 'application', 'database')])


class Stubs:
    """Stand-ins for prisma/litellm so the prelude runs offline; the originals would shell out."""
    def __init__(self):
        self.platform = types.ModuleType('prisma.binaries.platform')
        self.platform.binary_platform = mock.Mock(side_effect=AssertionError('probe must not run'))
        self.toolchain = types.ModuleType('litellm_proxy_extras.prisma_toolchain')
        self.toolchain.prisma_cli_available = mock.Mock(return_value=True)
        self.cli = types.ModuleType('litellm.proxy.proxy_cli')
        self.cli.run_server = mock.Mock()
        self.modules = {'prisma': types.ModuleType('prisma'), 'prisma.binaries': types.ModuleType('prisma.binaries'),
                        'prisma.binaries.platform': self.platform, 'litellm_proxy_extras': types.ModuleType('litellm_proxy_extras'),
                        'litellm_proxy_extras.prisma_toolchain': self.toolchain, 'litellm': types.ModuleType('litellm'),
                        'litellm.proxy': types.ModuleType('litellm.proxy'), 'litellm.proxy.proxy_cli': self.cli}
        self.modules['prisma'].binaries = self.modules['prisma.binaries']; self.modules['prisma.binaries'].platform = self.platform
        self.modules['litellm_proxy_extras'].prisma_toolchain = self.toolchain

    def run(self, prelude, versions):
        argv = ['-c', '--config', '/configuration/litellm-vertex.yaml', '--host', '0.0.0.0', '--port', '4000']
        with mock.patch.dict(sys.modules, self.modules), mock.patch.object(sys, 'argv', list(argv)), \
                mock.patch('importlib.metadata.version', side_effect=lambda name: versions[name]), \
                mock.patch.object(subprocess, 'run', side_effect=AssertionError('no subprocess')), \
                mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('no subprocess')):
            exec(compile(prelude, '<prelude>', 'exec'), {'__name__': '__main__'})
            return list(sys.argv)


class GatewayPrismaStartup(unittest.TestCase):
    def setUp(self):
        self.gateway = load('supervise-synthetic-demo-gateway')
        self.current = dict(self.gateway.REVIEWED_TOOLCHAIN)

    def test_reviewed_versions_are_exact(self):
        self.assertEqual(self.gateway.REVIEWED_TOOLCHAIN, {'litellm': '1.104.0', 'prisma': '0.15.0'})
        self.assertEqual(self.gateway.PRISMA_BINARY_PLATFORM, 'debian-openssl-3.0.x')

    def test_prelude_replaces_exactly_two_functions_then_runs_server(self):
        tree = ast.parse(self.gateway.PROXY_PRELUDE)
        assigned = [ast.unparse(t) for node in ast.walk(tree) if isinstance(node, ast.Assign) for t in node.targets]
        self.assertEqual(assigned, ['prisma_platform.binary_platform', 'prisma_toolchain.prisma_cli_available', 'sys.argv'])
        imports = sorted(alias.name if isinstance(node, ast.Import) else node.module + '.' + alias.name
                         for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names)
        self.assertEqual(imports, ['importlib.metadata.version', 'litellm.proxy.proxy_cli.run_server', 'litellm_proxy_extras.prisma_toolchain',
                                   'prisma.binaries.platform', 'sys'])
        self.assertEqual(ast.unparse(tree.body[-1]), 'run_server()')
        self.assertNotIn('environ', self.gateway.PROXY_PRELUDE)

    def test_current_versions_pin_platform_and_disable_prisma_cli_without_subprocess(self):
        stubs = Stubs()
        argv = stubs.run(self.gateway.PROXY_PRELUDE, self.current)
        self.assertEqual(stubs.platform.binary_platform(), 'debian-openssl-3.0.x')  # no cat / openssl probe
        self.assertIs(stubs.toolchain.prisma_cli_available(), False)  # no schema diff, migrations or nodeenv
        stubs.cli.run_server.assert_called_once_with()
        self.assertEqual(argv, ['/app/proxy.py', '--config', '/configuration/litellm-vertex.yaml', '--host', '0.0.0.0', '--port', '4000'])

    def test_version_drift_refuses_before_any_replacement(self):
        for name, drifted in (('litellm', '1.104.1'), ('prisma', '0.15.1'), ('litellm', '1.103.9')):
            stubs = Stubs(); original = stubs.platform.binary_platform
            with self.assertRaisesRegex(SystemExit, 'gateway:toolchain_unreviewed:' + name):
                stubs.run(self.gateway.PROXY_PRELUDE, dict(self.current, **{name: drifted}))
            self.assertIs(stubs.platform.binary_platform, original)
            self.assertTrue(stubs.toolchain.prisma_cli_available())
            stubs.cli.run_server.assert_not_called()

    def test_supervisor_guard_and_its_order(self):
        self.gateway.require_reviewed_toolchain(version=self.current.__getitem__)
        for name in self.current:
            with self.assertRaises(self.gateway.ToolchainUnreviewed):
                self.gateway.require_reviewed_toolchain(version=lambda n, name=name: self.current[n] + ('-drift' if n == name else ''))
        source = (ROOT / 'scripts/supervise-synthetic-demo-gateway.py').read_text()
        run = source[source.index('def run():'):]
        self.assertLess(run.index('require_reviewed_toolchain()'), run.index("'gateway-started'"))
        self.assertIn('"code":"GATEWAY_TOOLCHAIN_UNREVIEWED"', source)

    def test_child_command_environment_and_contract_otherwise_unchanged(self):
        source = (ROOT / 'scripts/supervise-synthetic-demo-gateway.py').read_text()
        self.assertIn("child = subprocess.Popen(['/usr/local/bin/python3.12', '-c', PROXY_PRELUDE,\n"
                      "            '--config', '/configuration/litellm-vertex.yaml', '--host', '0.0.0.0', '--port', '4000'],\n"
                      "            env=environment, stdout=log, stderr=log, start_new_session=True)", source)
        self.assertNotIn("'/app/proxy.py',\n", source)
        self.assertIn("environment = dict(os.environ, LITELLM_MASTER_KEY=config['master_key'],\n"
                      "                       LITELLM_SALT_KEY=config['salt_key'], DATABASE_URL=config['database_url'],\n"
                      "                       PORTFOLIO_VERTEX_PROJECT=config['project_id'])", source)
        self.assertIn("print(json.dumps({'gateway_stopped': True, 'reason': reason, 'restarts': 0,", source)

    def test_only_gateway_request_changes_and_rendering_is_deterministic(self):
        subject = bundle()
        self.assertEqual(subject, bundle())
        normal = copy.deepcopy(subject)
        gateway = next(x for x in normal['items'] if x['kind'] == 'Pod' and x['metadata']['name'] == 'gateway')
        container = gateway['spec']['containers'][0]
        self.assertEqual(container['resources'], {'requests': {'cpu': '100m', 'memory': '512Mi'}, 'limits': {'cpu': '1000m', 'memory': '768Mi'}})
        self.assertEqual(container['args'][1], (ROOT / 'scripts/supervise-synthetic-demo-gateway.py').read_text())
        self.assertEqual(gateway['metadata']['annotations']['portfolio.example/program-sha256'], hashlib.sha256(container['args'][1].encode()).hexdigest())
        gateway['metadata']['annotations']['portfolio.example/program-sha256'] = '<gateway-program>'
        container['args'][1] = '<gateway-program>'; container['resources']['requests']['memory'] = '<gateway-request>'
        for item in normal['items']:
            if item['kind'] in ('Pod', 'Job'):
                for init in (item['spec'] if item['kind'] == 'Pod' else item['spec']['template']['spec']).get('initContainers', []):
                    if init['name'] == 'stage-private-admission':
                        init['args'][1] = '<staging-program>'
        self.assertEqual(hashlib.sha256(json.dumps(normal, sort_keys=True).encode()).hexdigest(), NORMALIZED_BUNDLE_SHA256)
        others = [c for x in subject['items'] if x['kind'] in ('Pod', 'Job') and x['metadata']['name'] not in ('gateway', 'database')
                  for c in (x['spec'] if x['kind'] == 'Pod' else x['spec']['template']['spec'])['containers']]
        self.assertTrue(others and all(c['resources']['requests']['memory'] == '128Mi' for c in others))
        limits = next(x for x in subject['items'] if x['kind'] == 'LimitRange')['spec']['limits'][0]
        self.assertEqual((limits['max']['memory'], limits['default']['memory'], limits['defaultRequest']['memory']), ('768Mi', '768Mi', '128Mi'))


if __name__ == '__main__':
    unittest.main()
