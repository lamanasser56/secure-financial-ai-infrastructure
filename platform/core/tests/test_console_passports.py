"""Current passport declarations and the actual offline recording commands."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from agent_platform import onboarding
from test_console import make, ops_answers

REPO = Path(__file__).resolve().parents[3]


class PassportDeclarations(unittest.TestCase):
    def test_ops_proposes_and_declares_the_separate_executor_authority(self):
        console = make()
        ops = next(a for a in console.agents()['agents'] if a['kind'] == 'platform')
        self.assertIn('no mutation authority', ops['description'])
        actions = [t for t in ops['tools'] if t['access'] == 'approval']
        self.assertTrue(actions)
        for action in actions:
            self.assertTrue(action['description'].startswith('Propose '))
            self.assertIn('approval executor', action['description'])
        check = next(g for g in console.onboarding('ops-agent')['guarantees'] if g['id'] == 'approval')
        self.assertEqual((check['state'], check['basis']), ('declared', 'manifest'))
        self.assertEqual(check['source'], 'platform/core/src/agent_platform/ops/authority.json')
        self.assertTrue((REPO / check['source']).is_file())

    def test_ready_workloads_only_support_an_admission_inference(self):
        console = make()
        for name in ('financial', 'platform-guide'):
            check = next(g for g in console.onboarding(name)['guarantees'] if g['id'] == 'image')
            self.assertEqual(check['title'], 'Image admission')
            self.assertEqual((check['state'], check['basis']), ('verified', 'inference'))
            self.assertIn('inferred', check['detail'])
        own = next(g for g in console.onboarding('ops-agent')['guarantees'] if g['id'] == 'image')
        self.assertEqual(own['state'], 'declared')
        self.assertIn('does not verify signatures', own['detail'])
        self.assertNotIn('images.json', own['source'])

    def test_a_missing_worker_or_unavailable_source_cannot_infer_image_admission(self):
        answers = ops_answers()
        del answers['/v1/snapshot']['findings']['agent-financial.agent-u3']
        for console in (make(answers), make({})):
            check = next(g for g in console.onboarding('financial')['guarantees'] if g['id'] == 'image')
            self.assertEqual((check['state'], check['basis']), ('declared', 'manifest'))
            self.assertIn('signature not verified here', check['detail'])


class RecordedOnboardCommand(unittest.TestCase):
    def test_current_example_matches_documented_rules_and_make_rejects_without_generation(self):
        console = make()
        example = console.example()
        before = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (REPO / 'platform/core/kubernetes').rglob('*.yaml')}
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code = onboarding.check_file(REPO / example['file'], as_json=True)
        outcome = json.loads(stream.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(outcome['result'], 'REJECTED')
        self.assertEqual(len(outcome['reasons']), 5)
        docs = (REPO / 'docs/console/onboarding-review.md').read_text()
        run = subprocess.run(['make', 'onboard-check', 'F=' + example['file'], 'PYTHON=' + sys.executable],
                             cwd=REPO, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(run.returncode, 0)
        for reason in outcome['reasons']:
            self.assertIn(reason, docs)
            self.assertIn(reason, run.stdout)
        self.assertIn('Nothing was generated.', run.stdout)
        self.assertIn('five rule messages', example['text'])
        self.assertEqual(example['text'], (REPO / example['file']).read_text())
        after = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (REPO / 'platform/core/kubernetes').rglob('*.yaml')}
        self.assertEqual(before, after)


class SupportedForwards(unittest.TestCase):
    def test_current_manifests_select_the_trusted_financial_frontdoor_and_guide(self):
        # Exercise the actual owner command composition, replacing every external action.
        sys.path.insert(0, str(REPO / 'platform/clouds/gke'))
        import lifecycle
        manifests = onboarding.load_all()
        for name, namespace, target in [('financial', 'apps', 'financial-frontdoor'),
                                        ('platform-guide', 'agent-platform-guide', 'agent')]:
            with self.subTest(agent=name):
                with patch.object(lifecycle, 'kubeconfig') as config, patch.object(lifecycle.os, 'execv') as execute, \
                     patch.object(lifecycle, 'run', side_effect=AssertionError('no cloud command')), \
                     contextlib.redirect_stdout(io.StringIO()) as out:
                    lifecycle.agent_forward(name)
                config.assert_called_once_with()
                port = str(manifests[name]['runtime']['port'])
                args = execute.call_args.args[1]
                self.assertEqual(args[-7:], ['-n', namespace, 'port-forward', '--address', '127.0.0.1', 'deployment/' + target, port + ':' + port])
                self.assertEqual(json.loads(out.getvalue())['open'], 'http://127.0.0.1:' + port + '/')
                self.assertIn('http://127.0.0.1:' + port + '/', (REPO / 'docs/console/onboarding-review.md').read_text())

    def test_console_forward_stays_on_the_documented_loopback_port(self):
        sys.path.insert(0, str(REPO / 'platform/clouds/gke'))
        import lifecycle
        with patch.object(lifecycle, 'kubeconfig') as config, patch.object(lifecycle.os, 'execv') as execute:
            lifecycle.port_forward()
        config.assert_called_once_with()
        self.assertEqual(execute.call_args.args[1][-7:],
                         ['-n', 'apps', 'port-forward', '--address', '127.0.0.1', 'deployment/app', '8080:8080'])


if __name__ == '__main__':
    unittest.main()
