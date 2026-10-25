"""Facts follow the exact selected render, never the old shipped base or arbitrary cloud metadata."""
from copy import deepcopy
import importlib.util
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from agent_platform import console, onboarding, release_facts

ROOT = Path(__file__).resolve().parents[3]
SOURCE = 'd' * 40


class ReleaseFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts = release_facts.repository()

    def test_source_composition_is_explicitly_unbound(self):
        self.assertFalse(self.facts['bound_to_release'])
        self.assertIsNone(self.facts['source_commit'])
        self.assertEqual(set(self.facts['agents']), set(onboarding.load_all()))
        policies = [d for d in self.facts['documents'] if d['kind'] == 'NetworkPolicy']
        self.assertTrue(any('node-local-dns' in json.dumps(d) for d in policies))

    def selected(self):
        spec = importlib.util.spec_from_file_location('facts_render', ROOT / 'platform/clouds/gke/render.py')
        render = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(render)
        project = 'render-fixture'
        lock = json.loads((ROOT / 'platform/clouds/gke/release-rc1.lock.json').read_text())
        lock['registry'] = lock['registry'].replace('PROJECT_ID', project)
        lock['source_commit'] = SOURCE
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lock.json'
            path.write_text(json.dumps(lock))
            from types import SimpleNamespace
            text, _ = render.render(SimpleNamespace(images_lock=path, project_id=project,
                control_plane_cidr='172.16.0.16/28', gateway_gsa='fixture-gateway@' + project + '.iam.gserviceaccount.com',
                redactor_gsa='fixture-redactor@' + project + '.iam.gserviceaccount.com',
                kubectl=str(ROOT / '.cache/envtest-v1.35.0/kubectl')))
        return list(yaml.safe_load_all(text)), lock

    def test_selected_render_is_mounted_content_addressed_and_secret_free(self):
        docs, lock = self.selected()
        cm = next(d for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'].startswith(release_facts.NAME))
        facts = release_facts.validate(json.loads(cm['data']['console.json']))
        self.assertEqual(facts['source_commit'], SOURCE)
        self.assertTrue(facts['bound_to_release'])
        text = json.dumps(facts)
        for private in ('render-fixture', 'pkg.dev', 'gserviceaccount', 'bootstrap.json', 'api_key', 'private_key', 'def do_POST('):
            self.assertNotIn(private, text)
        app = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'app')
        pod = app['spec']['template']
        mount = next(v for v in pod['spec']['volumes'] if v['name'] == 'release-facts')
        self.assertEqual(mount['configMap']['name'], cm['metadata']['name'])
        self.assertTrue(next(m for m in pod['spec']['containers'][0]['volumeMounts'] if m['name'] == 'release-facts')['readOnly'])
        before = (cm['metadata']['name'], deepcopy(pod['metadata']['annotations']))
        release_facts.install(docs, onboarding.load_all(), lock, private_values=('render-fixture',))
        self.assertEqual((cm['metadata']['name'], pod['metadata']['annotations']), before)
        policy = next(d for d in docs if d['kind'] == 'NetworkPolicy' and d['metadata']['name'] == 'agent')
        policy['spec']['egress'].append({'to': [{'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'changed'}}}]})
        release_facts.install(docs, onboarding.load_all(), lock, private_values=('render-fixture',))
        self.assertNotEqual(cm['metadata']['name'], before[0])
        self.assertNotEqual(pod['metadata']['annotations'], before[1])
        self.assertEqual(mount['configMap']['name'], cm['metadata']['name'])

    def test_stale_policy_or_wrong_mount_cannot_pass_render_validation(self):
        docs, _ = self.selected()
        release_facts.verify(docs)
        changed = deepcopy(docs)
        policy = next(d for d in changed if d['kind'] == 'NetworkPolicy')
        policy['spec']['policyTypes'] = ['Ingress']
        with self.assertRaisesRegex(ValueError, 'do not match'):
            release_facts.verify(changed)
        app = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'app')
        volume = next(v for v in app['spec']['template']['spec']['volumes'] if v['name'] == 'release-facts')
        volume['configMap']['name'] = 'stale-facts'
        with self.assertRaisesRegex(ValueError, 'mount or rollout'):
            release_facts.verify(docs)

    def test_all_worker_members_and_replicas_come_from_selected_facts(self):
        from test_console import NOW, finding
        facts = deepcopy(self.facts)
        workers = [d for d in facts['documents'] if d['kind'] == 'Deployment' and d['metadata']['namespace'] == 'agent-financial']
        workers[0]['metadata']['name'] = 'new-worker'
        snapshot = {'findings': {'agent-financial.' + d['metadata']['name']: finding('agent-financial', d['metadata']['name']) for d in workers}}
        c = console.Console(lambda path: snapshot if path == '/v1/snapshot' else None, facts=facts, clock=lambda: NOW)
        profile = next(a for a in c.agents()['agents'] if a['name'] == 'financial')
        self.assertEqual((profile['replicas'], profile['live']['pods_ready']), (len(workers), len(workers)))
        del snapshot['findings']['agent-financial.new-worker']
        snapshot['findings']['agent-financial.agent'] = finding('agent-financial', 'agent')
        c._cache.clear()
        profile = next(a for a in c.agents()['agents'] if a['name'] == 'financial')
        self.assertEqual(profile['health']['state'], 'not_ready')
        self.assertEqual(profile['live']['desired'], len(workers))

    def test_packaged_app_refuses_missing_facts_and_does_not_fall_back_to_source(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(console, 'HERE', Path(tmp) / 'src/agent_platform/console.py'):
            (Path(tmp) / 'agents').mkdir()
            with patch.object(release_facts, 'repository', side_effect=AssertionError('no source fallback')):
                with self.assertRaisesRegex(ValueError, 'mounted release facts required'):
                    console.Console(lambda _: None, facts_path=Path(tmp) / 'missing.json')

    def test_browser_source_links_use_only_the_reported_immutable_commit(self):
        script = """
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const window = {}, document = {addEventListener() {}};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {window, document});
const c = window.Console, file = 'platform/core/src/agent_platform/console.py';
assert.equal(c.codeURL(file), null);
c.captureSource({headers: {get: () => 'd'.repeat(40)}});
assert.equal(c.codeURL(file), 'https://github.com/lamanasser56/secure-financial-ai-infrastructure/blob/' + 'd'.repeat(40) + '/' + file);
for (const value of [null, 'main', 'd'.repeat(39), 'D'.repeat(40), 'x'.repeat(40)]) {
  c.captureSource({headers: {get: () => value}});
  assert.equal(c.codeURL(file), null);
}
"""
        subprocess.run(['node', '-e', script, str(ROOT / 'platform/core/ui/core.js')], check=True)

    def test_unknown_or_malformed_facts_do_not_become_release_evidence(self):
        for mutate in (lambda f: f.update(schema_version=2), lambda f: f.update(extra='unexpected'),
                       lambda f: f.update(source_commit='main'), lambda f: f['documents'].append({'kind': 'Secret', 'metadata': {}})):
            facts = deepcopy(self.facts)
            mutate(facts)
            with self.assertRaises(ValueError):
                release_facts.validate(facts)


if __name__ == '__main__':
    unittest.main()
