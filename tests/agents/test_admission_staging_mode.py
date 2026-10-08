"""Private admission staging keeps exactly 0700 directories even when fsGroup marks the volume setgid."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# Bundle of 66103697 with only the staging init program masked.
NORMALIZED_BUNDLE_SHA256 = '034238141abe8921e7acc797e35013cc1b57e205e583e4af746ca0815b8a9e63'


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def redactor_journal():
    """The redactor's own Journal class; only its SDP runtime imports are stubbed."""
    stubs = {name: types.ModuleType(name) for name in ('runtime', 'runtime.phase3', 'runtime.phase3.google_sdp_adapter',
                                                       'runtime.phase3.sdp_context_policy')}
    stubs['runtime.phase3.google_sdp_adapter'].ContentAttemptBudget = object
    stubs['runtime.phase3.google_sdp_adapter'].GoogleSDPFailure = type('GoogleSDPFailure', (Exception,), {})
    stubs['runtime.phase3.sdp_context_policy'].GoogleSDPContextRedactor = object
    with mock.patch.dict(sys.modules, stubs):
        namespace = {'__name__': 'redactor'}
        exec(compile((ROOT / 'scripts/serve-synthetic-demo-redactor.py').read_text(), 'redactor', 'exec'), namespace)
    return namespace['Journal']


class AdmissionStagingMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.staging = load('stage-synthetic-demo-admission')
        for name in ('projected', 'staging', 'state-staging'):
            (self.root / name).mkdir()
        (self.root / 'projected/redactor-server.json').write_text('{"synthetic": true}\n')
        real = Path
        self.patch = mock.patch.object(self.staging, 'Path', lambda value: real(str(self.root) + value))
        self.patch.start()
        self.old_umask = os.umask(0o077)

    def tearDown(self):
        os.umask(self.old_umask); self.patch.stop(); self.tmp.cleanup()

    def volumes(self, mode):
        for name in ('staging', 'state-staging'):
            os.chmod(self.root / name, mode)  # what the kubelet leaves on an fsGroup-managed emptyDir

    def modes(self):
        return {name: stat.S_IMODE((self.root / name / 'private').lstat().st_mode) for name in ('staging', 'state-staging')}

    def test_setgid_volume_still_gives_exact_0700_and_the_redactor_journal_accepts_it(self):
        self.volumes(0o2770)
        self.assertTrue((self.root / 'staging').stat().st_mode & stat.S_ISGID)
        self.staging.stage()
        self.assertEqual(self.modes(), {'staging': 0o700, 'state-staging': 0o700})
        self.assertEqual(stat.S_IMODE((self.root / 'staging/private/redactor-server.json').lstat().st_mode), 0o600)
        redactor_journal()(self.root / 'state-staging/private', 0)  # the window-12 failure point
        self.assertTrue((self.root / 'state-staging/private/sdk-reservations').is_file())

    def test_inherited_setgid_is_what_the_journal_rejects(self):
        self.volumes(0o2770)
        probe = self.root / 'state-staging/probe'; probe.mkdir(mode=0o700)  # the previous mkdir-only behaviour
        self.assertEqual(stat.S_IMODE(probe.lstat().st_mode), 0o2700)
        with self.assertRaises(ValueError):
            redactor_journal()(probe, 0)

    def test_plain_volume_unchanged(self):
        self.volumes(0o770)
        self.staging.stage()
        self.assertEqual(self.modes(), {'staging': 0o700, 'state-staging': 0o700})

    def test_admission_rules_unchanged(self):
        (self.root / 'projected/unexpected.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.staging.stage()
        self.tmp.cleanup(); self.setUp()
        (self.root / 'projected/redactor-server.json').unlink()
        with self.assertRaises(ValueError):  # nothing to copy
            self.staging.stage()
        self.tmp.cleanup(); self.setUp()
        outside = self.root / 'outside.json'; outside.write_text('{}')
        (self.root / 'projected/gateway.json').symlink_to(outside)
        with self.assertRaises(ValueError):  # symlink leaving the projection
            self.staging.stage()

    def test_only_the_staging_program_changes_in_the_bundle(self):
        render = load('render-synthetic-demo-bundle')
        prefix = 'us-east1-docker.pkg.dev/project-fixture/sdp-evaluation-images/agent-demo-'
        subject = render.bundle('project-fixture', *[prefix + n + '@sha256:' + 'a' * 64 for n in ('gateway', 'application', 'database')])
        program = (ROOT / 'scripts/stage-synthetic-demo-admission.py').read_text()
        normal = copy.deepcopy(subject); staged = 0
        for item in normal['items']:
            if item['kind'] in ('Pod', 'Job'):
                spec = item['spec'] if item['kind'] == 'Pod' else item['spec']['template']['spec']
                for init in spec.get('initContainers', []):
                    if init['name'] == 'stage-private-admission':
                        self.assertEqual(init['args'][1], program); init['args'][1] = '<staging-program>'; staged += 1
        self.assertEqual(staged, 5)
        self.assertEqual(hashlib.sha256(json.dumps(normal, sort_keys=True).encode()).hexdigest(), NORMALIZED_BUNDLE_SHA256)


if __name__ == '__main__':
    unittest.main()
