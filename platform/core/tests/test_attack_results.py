"""Live attack results: one closed shape written by `make attack` into ConfigMap apps/attack-results and read by the console
from a read-only mount; the bundled recorded run is the fallback. No secret or project ID can pass through."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import yaml

from agent_platform import attack_results
import test_console as t

REPO = Path(__file__).resolve().parents[3]
PROJECT = 'demo-project-123456'
RUN = {'suite': 'agent-platform-attacks', 'cluster': 'agent-platform', 'completed_at': '2026-11-01T10:20:30.123456+00:00',
       'gateway_key_spend_usd': {'before': 0.1, 'after': 0.2}, 'note': 'free text that must not travel',
       'results': [{'case': 'financial_setup', 'result': 'PASS', 'at': '2026-11-01T10:00:00.000001+00:00', 'evidence': {}},
                   {'case': 'unsigned_image_rejected', 'result': 'PASS', 'at': '2026-11-01T10:05:00+00:00',
                    'evidence': {'image': 'us-east1-docker.pkg.dev/' + PROJECT + '/r/x@sha256:' + '0' * 64, 'key': 'sk-' + 'Z' * 40}},
                   {'case': 'egress_containment', 'result': 'FAIL', 'at': '2026-11-01T10:06:00Z', 'evidence': {'detail': PROJECT}}]}


class Shape(unittest.TestCase):
    def test_only_case_result_and_time_survive(self):
        clean = attack_results.sanitize(RUN)
        self.assertEqual(set(clean), {'suite', 'completed_at', 'results'})
        self.assertTrue(all(set(r) == {'case', 'result', 'at'} for r in clean['results']))
        text = json.dumps(clean)
        for leak in (PROJECT, 'sk-', 'pkg.dev', 'free text', 'spend'):
            self.assertNotIn(leak, text)

    def test_a_value_that_could_carry_a_project_id_or_secret_is_refused(self):
        for bad in ({'case': PROJECT, 'result': 'PASS', 'at': '2026-11-01T10:05:00Z'},          # hyphens: not a case id
                    {'case': 'ok_case', 'result': 'PASS ' + PROJECT, 'at': '2026-11-01T10:05:00Z'},
                    {'case': 'ok_case', 'result': 'PASS', 'at': '2026-11-01T10:05:00Z ' + PROJECT},
                    {'case': 'sk_' + 'z' * 90, 'result': 'PASS', 'at': '2026-11-01T10:05:00Z'}):   # too long for a case id
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                attack_results.sanitize(dict(RUN, results=[bad]))
        for bad in (None, {}, {'results': []}, dict(RUN, completed_at=PROJECT), dict(RUN, results=RUN['results'] * 30)):
            with self.assertRaises(ValueError):
                attack_results.sanitize(bad)

    def test_the_configmap_holds_the_sanitized_json_and_nothing_else(self):
        cm = attack_results.configmap(RUN)
        self.assertEqual((cm['kind'], cm['metadata']['name'], cm['metadata']['namespace']), ('ConfigMap', 'attack-results', 'apps'))
        self.assertEqual(list(cm['data']), ['attack-suite.json'])
        self.assertEqual(json.loads(cm['data']['attack-suite.json']), attack_results.sanitize(RUN))
        self.assertNotIn(PROJECT, json.dumps(cm))

    def test_make_attack_publishes_only_the_configmap(self):
        sys.path.insert(0, str(REPO / 'platform/clouds/gke'))
        import attack_suite
        sent = []
        with mock.patch.object(attack_suite, 'k', side_effect=lambda *a, input=None: sent.append((a, input)) or mock.Mock(returncode=0)), \
                mock.patch('sys.stdout', new=io.StringIO()) as out:
            self.assertTrue(attack_suite.publish(RUN))
        self.assertEqual(sent[0][0], ('apply', '-f', '-'))
        self.assertEqual(json.loads(sent[0][1]), attack_results.configmap(RUN))
        self.assertNotIn(PROJECT, sent[0][1] + out.getvalue())
        with mock.patch.object(attack_suite, 'k') as k, mock.patch('sys.stdout', new=io.StringIO()) as out:
            self.assertFalse(attack_suite.publish({'results': 'not a list'}))
        k.assert_not_called()  # a report that does not fit the shape is not written at all
        self.assertEqual(out.getvalue(), '')  # main reports publication failure and exits nonzero


class Console(unittest.TestCase):
    def console(self, live_text=None):
        tmp = tempfile.mkdtemp()
        path = Path(tmp) / 'attack-suite.json'
        if live_text is not None:
            path.write_text(live_text)
        c = t.make()
        c.live_attacks = path
        return c

    def test_live_run_is_preferred_and_labelled(self):
        data = self.console(json.dumps(attack_results.sanitize(RUN))).attacks()
        self.assertEqual((data['source'], data['file'], data['completed_at']), ('live', 'ConfigMap apps/attack-results', RUN['completed_at']))
        self.assertEqual([r['case'] for r in data['results']], ['unsigned_image_rejected', 'egress_containment'])
        self.assertEqual((data['stopped'], data['total']), (1, 2))
        self.assertFalse([r for r in data['results'] if 'note' in r])  # the owner's note is about the recorded run only

    def test_missing_or_malformed_configmap_falls_back_to_the_recorded_run(self):
        for live in (None, 'not json', json.dumps({'results': 'x'}), json.dumps(dict(RUN, completed_at='yesterday'))):
            with self.subTest(live=live):
                data = self.console(live).attacks()
                self.assertEqual((data['source'], data['file']), ('recorded', 'docs/evidence/attack-suite.json'))
                self.assertTrue(data['available'])

    def test_a_full_report_in_the_configmap_is_still_reduced_to_the_closed_shape(self):
        data = self.console(json.dumps(RUN)).attacks()  # even if someone wrote the raw report, nothing else is served
        self.assertEqual(data['source'], 'live')
        self.assertNotIn(PROJECT, json.dumps(data))
        self.assertNotIn('sk-', json.dumps(data))


class Manifest(unittest.TestCase):
    def test_the_app_mounts_it_read_only_and_optional_with_no_new_rbac(self):
        docs = [d for d in yaml.safe_load_all((REPO / 'platform/core/kubernetes/apps/workloads.yaml').read_text()) if d]
        app = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'app')['spec']['template']['spec']
        volume = next(v for v in app['volumes'] if v['name'] == 'attack-results')
        self.assertEqual(volume['configMap'], {'name': 'attack-results', 'optional': True, 'defaultMode': 0o444})
        mount = next(m for m in app['containers'][0]['volumeMounts'] if m['name'] == 'attack-results')
        self.assertEqual((mount['mountPath'], mount['readOnly']), ('/attack-results', True))
        self.assertFalse(app['automountServiceAccountToken'])
        for path in (REPO / 'platform/core/kubernetes').rglob('*.yaml'):
            for d in yaml.safe_load_all(path.read_text()):
                if d and d.get('kind') == 'Role' and d['metadata'].get('namespace') == 'apps':
                    self.assertFalse(any('configmaps' in r.get('resources', []) for r in d.get('rules', [])), path)
        self.assertEqual(attack_results.CONFIGMAP, volume['configMap']['name'])


if __name__ == '__main__':
    unittest.main()
