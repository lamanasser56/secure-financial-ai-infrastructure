"""One inventory/source owner; actual HTTP responses and the Python image path layout."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

from agent_platform import ui_assets

ROOT = Path(__file__).resolve().parents[3]
FIN = ROOT / 'platform/agents/financial/finance_agent/ui'


class SharedAssets(unittest.TestCase):
    def test_private_ui_has_no_parallel_shared_sources(self):
        self.assertEqual({p.name for p in FIN.iterdir()}, {'app.js', 'index.html'})
        manifest = ui_assets.inventory()
        self.assertEqual(set(manifest), {'/core.js', '/style.css'} | {'/typeface/' + p.name for p in (ui_assets.ROOT / 'typeface').glob('*.woff2')})
        for route in manifest:
            value = ui_assets.read(route)
            self.assertEqual(value[0], (ui_assets.ROOT / route[1:]).read_bytes())

    def test_unknown_and_traversal_routes_cannot_read_another_file(self):
        for route in ('/shared-assets.json', '/typeface/LICENSE-barlow.txt', '/typeface/nope.woff2',
                      '/../core.js', '/typeface/../core.js', '/%2e%2e/core.js', '/core.js/x'):
            self.assertIsNone(ui_assets.read(route), route)

    def test_the_copied_python_sdk_resolves_the_actual_image_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary)
            module = image / 'platform/src/agent_platform/ui_assets.py'
            module.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / 'platform/core/src/agent_platform/ui_assets.py', module)
            target = image / 'platform/ui'
            target.mkdir()
            shutil.copyfile(ui_assets.ROOT / 'shared-assets.json', target / 'shared-assets.json')
            for route in ui_assets.inventory():
                output = target / route[1:]
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ui_assets.ROOT / route[1:], output)
            spec = importlib.util.spec_from_file_location('packaged_ui_assets', module)
            packaged = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(packaged)
            for route in ui_assets.inventory():
                self.assertEqual(packaged.read(route), ui_assets.read(route), route)
            outside = image / 'unowned.js'
            outside.write_text('not a shared asset')
            (target / 'core.js').unlink()
            (target / 'core.js').symlink_to(outside)
            self.assertIsNone(packaged.read('/core.js'))
