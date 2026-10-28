"""Current producer/consumer contract and explicit unbound history, with no historical fallback."""
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import yaml

from agent_platform import attack_results, release_facts
import test_console as t

REPO = Path(__file__).resolve().parents[3]
PROJECT = 'private-project-fixture'
AT = '2026-10-25T12:00:00+00:00'


def facts():
    return {'schema_version': 1, 'source_commit': 'a'*40, 'bound_to_release': True,
            'agents': {}, 'model': 'fixture', 'documents': [{'kind': 'Deployment',
                'metadata': {'namespace': 'apps', 'name': 'app'}, 'spec': {'template': {'spec': {
                    'containers': [{'name': 'app', 'image': 'sha256:'+'b'*64}]}}}}]}


def report(selected=None):
    return {'schema_version': attack_results.VERSION, 'suite': attack_results.SUITE, 'run_id': 'c'*32,
            'runner_commit': 'd'*40, 'release': release_facts.evidence_binding(selected or facts()),
            'completed_at': AT, 'private': PROJECT, 'results': [
                {'case': name, 'kind': meta[0], 'result': 'PASS', 'verdict': 'PASS', 'at': AT,
                 'evidence': {'password': 'sk-'+'Z'*40, 'raw': PROJECT}}
                for name, meta in attack_results.CASES.items()]}


def old_report():
    return {'suite': attack_results.SUITE, 'completed_at': AT, 'note': PROJECT,
            'results': [{'case': 'retired_check', 'result': 'PASS', 'at': AT, 'evidence': {'raw': PROJECT}}]}


class Shape(unittest.TestCase):
    def test_only_public_binding_closed_cases_and_metadata_survive(self):
        clean = attack_results.sanitize(report())
        self.assertEqual(set(clean), {'schema_version', 'suite', 'run_id', 'runner_commit', 'release', 'completed_at', 'results'})
        self.assertTrue(all(set(r) == {'case', 'kind', 'result', 'verdict', 'at', 'reason', 'facts'} for r in clean['results']))
        for secret in (PROJECT, 'sk-', 'password', 'raw'):
            self.assertNotIn(secret, json.dumps(clean))

    def test_v3_keeps_the_real_reason_and_closed_facts_only(self):
        run = report()
        run['results'][3].update(result='FAIL', verdict='NOT_EXERCISED',
                                 evidence={'reason': 'CONTROL_UNAVAILABLE', 'detail': 'active_turn_not_established'})
        run['results'][4]['evidence'] = {'forged_session_cookie': 401, 'lama_sees_sara_rows': False, 'code': 'OBJECT_CHANGED',
                                         'worker': 'agent-u2', 'request_id': 'e'*32, 'note': 'free text: ' + PROJECT,
                                         'project': PROJECT, 'api_key': 'abc', 'nested': {'session_token': 'x', 'checks': [{'forged_user': True}]}}
        clean = attack_results.sanitize(run)
        self.assertEqual(clean['results'][3]['reason'], 'active_turn_not_established')
        self.assertIsNone(clean['results'][4]['reason'])
        self.assertEqual(dict(map(tuple, clean['results'][4]['facts'])), {
            'forged_session_cookie': 401, 'lama_sees_sara_rows': False, 'code': 'OBJECT_CHANGED', 'worker': 'agent-u2',
            'request_id': 'e'*32, 'nested.checks.0.forged_user': True})
        self.assertNotIn(PROJECT, json.dumps(clean))
        # The ConfigMap round trip (writer sanitizes, console sanitizes again) keeps both.
        again = attack_results.view(json.loads(attack_results.configmap(run)['data'][attack_results.KEY]), run['release'])
        self.assertEqual(again['results'][3]['reason'], 'active_turn_not_established')
        self.assertEqual(again['results'][4]['facts'], clean['results'][4]['facts'])
        self.assertEqual([(i['case'], i['reason']) for i in again['incomplete']], [(run['results'][3]['case'], 'active_turn_not_established')])

    def test_a_reason_without_detail_falls_back_to_the_runner_category_and_never_to_free_text(self):
        run = report()
        run['results'][0].update(result='FAIL', verdict='NOT_EXERCISED', evidence={'reason': 'CONTROL_UNAVAILABLE'})
        run['results'][1].update(result='FAIL', verdict='FAIL', evidence={'reason': 'see ' + PROJECT})
        rows = attack_results.sanitize(run)['results']
        self.assertEqual((rows[0]['reason'], rows[1]['reason']), ('control_unavailable', 'not_recorded'))

    def test_a_hand_edited_configmap_cannot_smuggle_text_through_reason_or_facts(self):
        clean = attack_results.sanitize(report())
        for row in ({'reason': PROJECT}, {'reason': 'ok_reason'},  # a PASS row has no reason
                    {'facts': [['note', PROJECT]]}, {'facts': [['api_key', 'abc']]}, {'facts': [['x', 'y']] * 25}):
            bad = deepcopy(clean); bad['results'][0].update(row)
            with self.subTest(row=row), self.assertRaises(ValueError):
                attack_results.sanitize(bad)

    def test_version_2_reports_stay_readable_without_reasons(self):
        run = report(); run['schema_version'] = 2
        clean = attack_results.sanitize(run)
        self.assertEqual(clean['schema_version'], 2)
        self.assertTrue(all(set(r) == {'case', 'kind', 'result', 'verdict', 'at'} for r in clean['results']))
        self.assertEqual(attack_results.view(run, run['release'])['incomplete'], [])

    def test_missing_runner_identity_is_named_as_the_reason(self):
        run = report(); run['runner_commit'] = None
        value = attack_results.view(run, run['release'])
        self.assertFalse(value['complete'])
        self.assertEqual([i['reason'] for i in value['incomplete']], ['runner_commit_not_recorded'])

    def test_missing_duplicate_unknown_and_misclassified_cases_cannot_qualify(self):
        original = report()
        mutations = []
        missing = deepcopy(original); missing['results'].pop(); mutations.append(missing)
        duplicate = deepcopy(original); duplicate['results'][-1] = duplicate['results'][0]; mutations.append(duplicate)
        for key, value in (('case', PROJECT), ('kind', 'attack'), ('verdict', 'BLOCKED'), ('result', 'FAIL'), ('at', '2026-02-30T00:00:00Z')):
            altered = deepcopy(original); altered['results'][0][key] = value; mutations.append(altered)
        for key, value in (('run_id', PROJECT), ('runner_commit', PROJECT), ('suite', PROJECT), ('completed_at', 'yesterday'), ('schema_version', 999)):
            altered = deepcopy(original); altered[key] = value; mutations.append(altered)
        for bad in mutations:
            with self.subTest(bad=bad), self.assertRaises(ValueError): attack_results.sanitize(bad)

    def test_private_or_malformed_release_subjects_are_rejected(self):
        for key, value in (('id', PROJECT), ('source_commit', PROJECT), ('images', ['registry/'+PROJECT+'@sha256:'+'0'*64]), ('images', [])):
            altered = report(); altered['release'][key] = value
            with self.assertRaises(ValueError): attack_results.sanitize(altered)

    def test_not_exercised_is_separate_from_a_failed_security_check(self):
        run = report()
        run['results'][2].update(result='FAIL', verdict='NOT_EXERCISED')
        run['results'][3].update(result='FAIL', verdict='FAIL')
        value = attack_results.view(run, run['release'])
        self.assertEqual(value['binding'], 'current')
        self.assertFalse(value['complete'])
        self.assertEqual((value['summary']['attack']['failed'], value['summary']['attack']['not_exercised']), (1, 1))
        self.assertEqual(value['summary']['control']['passed'], 6)

    def test_source_image_or_declaration_change_breaks_the_release_match(self):
        run = report()
        self.assertEqual(attack_results.view(run, run['release'])['binding'], 'current')
        for field in ('source', 'image', 'declaration'):
            selected = facts()
            if field == 'source': selected['source_commit'] = 'e'*40
            if field == 'image': selected['documents'][0]['spec']['template']['spec']['containers'][0]['image'] = 'sha256:'+'f'*64
            if field == 'declaration': selected['documents'][0]['spec']['replicas'] = 2
            changed = release_facts.evidence_binding(selected)
            self.assertNotEqual(changed['id'], run['release']['id'])
            self.assertEqual(attack_results.view(run, changed)['binding'], 'different_release')
        selected = facts(); selected['bound_to_release'] = False
        self.assertIsNone(release_facts.evidence_binding(selected))
        self.assertEqual(attack_results.view(run, None)['binding'], 'unbound')

    def test_unbuilt_images_or_unknown_source_never_qualify_a_release(self):
        for missing in ('image','source'):
            selected = facts()
            if missing == 'image': selected['documents'][0]['spec']['template']['spec']['containers'][0]['image'] = 'unbuilt'
            else: selected['source_commit'] = None
            self.assertIsNone(release_facts.evidence_binding(selected))

    def test_historical_outcomes_are_unbound_and_never_relabelled_as_boundary_passes(self):
        data = attack_results.view(old_report(), report()['release'])
        self.assertEqual((data['binding'], data['complete']), ('historical', False))
        self.assertEqual(data['results'][0]['verdict'], 'RECORDED_PASS')
        self.assertEqual(data['summary']['attack']['passed'], 0)
        self.assertNotIn(PROJECT, json.dumps(data))
        self.assertNotIn('retired_check', json.dumps(data))

    def test_make_attack_publishes_the_current_closed_configmap_only(self):
        sys.path.insert(0, str(REPO/'platform/clouds/gke'))
        import attack_suite
        sent = []
        with mock.patch.object(attack_suite, 'k', side_effect=lambda *a, input=None: sent.append((a,input)) or mock.Mock(returncode=0)):
            self.assertTrue(attack_suite.publish(report()))
        self.assertEqual(sent[0][0], ('apply', '-f', '-'))
        cm = json.loads(sent[0][1])
        self.assertEqual(json.loads(cm['data'][attack_results.KEY]), attack_results.sanitize(report()))
        self.assertNotIn(PROJECT, sent[0][1])
        with mock.patch.object(attack_suite, 'k') as command, mock.patch('sys.stdout', new=io.StringIO()) as output:
            self.assertFalse(attack_suite.publish(old_report()))
        command.assert_not_called()
        self.assertEqual(output.getvalue(), '')

    def test_writer_inventory_has_one_kind_authority_and_all_required_cases(self):
        import attack_suite
        cases = attack_suite.build_cases({})
        self.assertEqual([(c.name,c.kind) for c in cases], [(name,meta[0]) for name,meta in attack_results.CASES.items()])


class Console(unittest.TestCase):
    def mounted(self, content=None):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name)/'attack-suite.json'
        if content is not None: path.write_text(content)
        console = t.make(); console.live_attacks = path; console.facts = facts()
        return console

    def test_mounted_report_is_bound_to_the_actual_selected_facts(self):
        data = self.mounted(json.dumps(report())).attacks()
        self.assertTrue(data['available'])
        self.assertEqual(data['binding'], 'current')
        self.assertEqual(data['source'], 'mounted')
        self.assertEqual(data['run_id'], 'c'*32)
        self.assertEqual(data['results'][0]['kind'], 'control')
        self.assertNotIn(PROJECT, json.dumps(data))

    def test_missing_or_invalid_current_mount_never_falls_back_to_bundled_success(self):
        for content, status in ((None, 'missing'), ('not json', 'invalid'), ('{}', 'invalid')):
            data = self.mounted(content).attacks()
            self.assertFalse(data['available'])
            self.assertEqual(data['status'], status)
            self.assertEqual(data['results'], [])

    def test_valid_preversioned_mount_is_explicit_history(self):
        data = self.mounted(json.dumps(old_report())).attacks()
        self.assertTrue(data['available'])
        self.assertEqual(data['binding'], 'historical')
        self.assertEqual(data['summary']['attack']['total'], 0)

    def test_current_render_all_runtime_subjects_are_bound_without_registry_identity(self):
        from test_release_facts import ReleaseFacts
        docs, _ = ReleaseFacts().selected()
        selected = release_facts.verify(docs)
        value = release_facts.evidence_binding(selected)
        def images(value):
            if isinstance(value,dict):
                for key,child in value.items():
                    if key == 'image' and isinstance(child,str): yield child
                    else: yield from images(child)
            elif isinstance(value,list):
                for child in value: yield from images(child)
        # Include Job and init-container subjects as well, so a future unique image
        # cannot quietly disappear from the public binding.
        expected = sorted({image.split('@')[-1] for image in images(docs)})
        self.assertEqual(value['images'], expected)
        self.assertNotIn('pkg.dev', json.dumps(value))


class Manifest(unittest.TestCase):
    def test_read_only_optional_mount_does_not_give_the_app_write_rbac(self):
        docs = [d for d in yaml.safe_load_all((REPO/'platform/core/kubernetes/apps/workloads.yaml').read_text()) if d]
        app = next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='app')['spec']['template']['spec']
        volume = next(v for v in app['volumes'] if v['name']=='attack-results')
        self.assertEqual(volume['configMap'], {'name':attack_results.CONFIGMAP,'optional':True,'defaultMode':0o444})
        mount = next(m for m in app['containers'][0]['volumeMounts'] if m['name']=='attack-results')
        self.assertEqual((mount['mountPath'],mount['readOnly']),('/attack-results',True))
        self.assertFalse(app['automountServiceAccountToken'])
        for path in (REPO/'platform/core/kubernetes').rglob('*.yaml'):
            for doc in yaml.safe_load_all(path.read_text()):
                if doc and doc.get('kind')=='Role' and doc['metadata'].get('namespace')=='apps':
                    self.assertFalse(any('configmaps' in r.get('resources',[]) for r in doc.get('rules',[])))


if __name__ == '__main__': unittest.main()
