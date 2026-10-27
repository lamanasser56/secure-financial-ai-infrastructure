"""The gateway image runs the reviewed prelude before LiteLLM: no unreviewed toolchain, no `cat`, no Prisma CLI."""
from pathlib import Path
import re
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

from agent_platform.programs import gateway_entry

ROOT = Path(__file__).resolve().parents[3]


def fake_modules(seen):
    platform = types.ModuleType('prisma.binaries.platform')
    platform.binary_platform = lambda: seen.append('cat /etc/os-release') or 'detected'
    toolchain = types.ModuleType('litellm_proxy_extras.prisma_toolchain')
    toolchain.prisma_cli_available = lambda: True
    cli = types.ModuleType('litellm.proxy.proxy_cli')

    def run_server():
        seen.append(('run_server', list(sys.argv), platform.binary_platform(), toolchain.prisma_cli_available()))
    cli.run_server = run_server
    modules = {'prisma': types.ModuleType('prisma'), 'prisma.binaries': types.ModuleType('prisma.binaries'),
               'prisma.binaries.platform': platform,
               'litellm_proxy_extras': types.ModuleType('litellm_proxy_extras'),
               'litellm_proxy_extras.prisma_toolchain': toolchain,
               'litellm': types.ModuleType('litellm'), 'litellm.proxy': types.ModuleType('litellm.proxy'),
               'litellm.proxy.proxy_cli': cli}
    modules['prisma'].binaries = modules['prisma.binaries']
    modules['prisma.binaries'].platform = platform
    modules['litellm_proxy_extras'].prisma_toolchain = toolchain
    modules['litellm'].proxy = modules['litellm.proxy']
    modules['litellm.proxy'].proxy_cli = cli
    return modules


class GatewayEntry(unittest.TestCase):
    def test_reviewed_toolchain_equals_the_gateway_lock(self):
        lock = (ROOT / 'requirements-gateway.txt').read_text()
        pins = dict(re.findall(r'^([a-z0-9-]+)==([^ \\\n]+)', lock, re.MULTILINE))
        self.assertEqual(gateway_entry.REVIEWED_TOOLCHAIN, {name: pins[name] for name in ('litellm', 'prisma')})

    def test_prelude_pins_platform_disables_cli_and_starts_with_fixed_arguments(self):
        seen = []
        versions = dict(gateway_entry.REVIEWED_TOOLCHAIN)
        with patch.dict(sys.modules, fake_modules(seen)), patch.object(gateway_entry, 'version', versions.get), \
                patch.object(sys, 'argv', ['gateway_entry']):
            gateway_entry.main()
        self.assertEqual(seen, [('run_server', ['/app/proxy.py', '--config', '/config/litellm.yaml', '--host', '0.0.0.0',
                                                '--port', '4001', '--num_workers', '1'], 'debian-openssl-3.0.x', False)])

    def test_unreviewed_toolchain_is_refused_before_anything_starts(self):
        for name in gateway_entry.REVIEWED_TOOLCHAIN:
            with self.subTest(name=name):
                seen = []
                versions = dict(gateway_entry.REVIEWED_TOOLCHAIN, **{name: '0.0.1'})
                with patch.dict(sys.modules, fake_modules(seen)), patch.object(gateway_entry, 'version', versions.get):
                    with self.assertRaisesRegex(SystemExit, 'gateway:toolchain_unreviewed:' + name):
                        gateway_entry.main()
                self.assertEqual(seen, [])

    def test_arguments_are_rejected(self):
        result = subprocess.run([sys.executable, '-m', 'agent_platform.programs.gateway_entry', '--port', '1'],
                                capture_output=True, text=True, cwd=ROOT,
                                env={'PYTHONPATH': str(ROOT / 'platform/core/src')})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('gateway:arguments_rejected', result.stderr)

    def test_image_runs_the_entry_and_its_runtime_has_no_shell_tools(self):
        dockerfile = (ROOT / 'docker/gateway/Dockerfile').read_text()
        runtime = dockerfile.split(' AS runtime', 1)[1]
        self.assertIn('ENTRYPOINT ["/usr/local/bin/python3.12", "-m", "agent_platform.programs.gateway_entry"]', runtime)
        self.assertIn('programs/gateway_entry.py', runtime)
        for forbidden in ('busybox', '/bin/sh', '/bin/cat', 'coreutils', 'uvicorn"'):
            self.assertNotIn(forbidden, runtime)
        self.assertRegex(dockerfile, r'FROM gcr\.io/distroless/base-debian13:nonroot@sha256:[0-9a-f]{64} AS runtime')


if __name__ == '__main__':
    unittest.main()
