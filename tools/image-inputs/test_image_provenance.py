"""The signed predicate is bound to hosted build inputs, not an engineering VM."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('image_provenance', ROOT / 'scripts/image-provenance.py')
provenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provenance)


class HostedPredicate(unittest.TestCase):
    SOURCE = 'a' * 40
    ARCHIVE = 'b' * 64
    PLAN = {'source_commit': SOURCE, 'images': [{
        'image': 'agent-platform-app', 'fingerprint': 'c' * 64,
        'materials': ['docker.io/library/python@sha256:' + 'd' * 64]}]}

    def test_exact_input_plan_and_archive_produce_portable_predicate(self):
        value = provenance.predicate(self.PLAN, 'agent-platform-app', self.SOURCE, self.ARCHIVE)
        self.assertEqual(value['schema'], 2)
        self.assertEqual(value['build_environment'], 'github-hosted:ubuntu-24.04')
        self.assertEqual(value['git_archive_sha256'], self.ARCHIVE)
        self.assertEqual(value['input_fingerprint'], 'c' * 64)
        self.assertIn(provenance.BUILDKIT, value['materials'])
        self.assertNotIn('worker', value)

    def test_source_image_archive_and_material_drift_fail_closed(self):
        for plan, image, source, archive in (
            (self.PLAN, 'other', self.SOURCE, self.ARCHIVE),
            (self.PLAN, 'agent-platform-app', 'e' * 40, self.ARCHIVE),
            (self.PLAN, 'agent-platform-app', self.SOURCE, 'wrong'),
            ({**self.PLAN, 'images': [*self.PLAN['images'], self.PLAN['images'][0]]},
             'agent-platform-app', self.SOURCE, self.ARCHIVE),
            ({**self.PLAN, 'images': [{**self.PLAN['images'][0], 'materials': ['z', 'a']}]},
             'agent-platform-app', self.SOURCE, self.ARCHIVE),
        ):
            with self.subTest(image=image, source=source, archive=archive):
                with self.assertRaises(ValueError):
                    provenance.predicate(plan, image, source, archive)
