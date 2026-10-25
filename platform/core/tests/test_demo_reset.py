"""make demo-reset (offline, fake kubectl): refuses a down or unready platform, asks first, never touches a Secret."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'clouds/gke'))
import demo_reset  # noqa: E402


class Kube:
    def __init__(self, ready=True, fail=None):
        self.ready, self.fail, self.calls = ready, fail, []

    def __call__(self, *args, input=None):
        self.calls.append((args, input))
        a = ' '.join(args)
        if self.fail and self.fail in a:
            return 1, ''
        if 'readyReplicas' in a:
            return (0, '1 1 1 1 1') if self.ready else (0, '')
        if 'exec' in args:
            return 0, 'redactor warm-up: ok\n'
        return 0, ''


def reset(kube, *, nodes=1, answer='yes'):
    lines, seeded = [], []
    r = demo_reset.Reset(kubectl=kube, nodes=lambda: nodes,
                         declared=('kind: Deployment\n', [('deployment', 'apps', 'app')]), seed=lambda: seeded.append(1),
                         ask=lambda prompt: answer, out=lines.append)
    return r, lines, seeded


class DemoReset(unittest.TestCase):
    def test_refuses_when_down_or_not_ready_and_changes_nothing(self):
        for kube, nodes in ((Kube(), 0), (Kube(), None), (Kube(ready=False), 1)):
            r, _, seeded = reset(kube, nodes=nodes)
            with self.assertRaises(demo_reset.Refused):
                r.run()
            self.assertFalse([c for c in kube.calls if 'readyReplicas' not in ' '.join(c[0])])
            self.assertEqual(seeded, [])

    def test_asks_first(self):
        kube = Kube()
        r, _, seeded = reset(kube, answer='no')
        with self.assertRaises(demo_reset.Refused):
            r.run()
        self.assertFalse([c for c in kube.calls if 'readyReplicas' not in ' '.join(c[0])])
        self.assertEqual(seeded, [])

    def test_steps_in_order_and_port_forwards(self):
        kube = Kube()
        r, lines, seeded = reset(kube)
        self.assertEqual(r.run(), 0)
        writes = [' '.join(c[0]) for c in kube.calls if 'readyReplicas' not in ' '.join(c[0])]
        self.assertTrue(writes[0].startswith('apply --server-side'))
        self.assertIn('rollout restart deployment/ops-agent', writes[2])
        self.assertEqual(seeded, [1])
        self.assertIn('exec deployment/app', writes[-1])
        self.assertIn('  make port-forward                # console:          http://127.0.0.1:8080/', lines)
        self.assertIn('  make agent-forward A=financial   # Financial Agent:  http://127.0.0.1:8081/', lines)

    def test_never_touches_a_secret_or_the_passphrase(self):
        kube = Kube()
        reset(kube)[0].run()
        for args, input in kube.calls:
            text = ' '.join(args) + (input or '')
            for word in ('secret', 'passphrase', 'operator_secret', 'delete', 'scale'):
                self.assertNotIn(word, text.replace("/secrets/app/app.json", ''))  # the warm-up reads the Pod's own mounted config

    def test_warm_up_sends_no_user_data(self):
        self.assertEqual(demo_reset.WARM_UP_TEXT, 'Demo warm-up sentence with no personal data.')
        self.assertIn(repr(demo_reset.WARM_UP_TEXT), demo_reset.WARM_UP)
        self.assertNotIn('print(c', demo_reset.WARM_UP)  # the key is never printed

    def test_a_refused_warm_up_is_incomplete_and_nothing_else_is_tried(self):
        kube = Kube(fail='exec')
        r, lines, seeded = reset(kube)
        with self.assertRaisesRegex(demo_reset.Refused, 'incomplete: redactor warm-up failed'):
            r.run()
        self.assertIn('FAILED redactor warm-up (kubectl exec was refused or failed; nothing was bypassed).', lines)
        self.assertFalse(any('Port-forwards' in line for line in lines))
        self.assertEqual(sum('exec' in c[0] for c in kube.calls), 1)  # one attempt, no other route

    def test_a_failed_step_stops(self):
        kube = Kube(fail='rollout restart')
        r, lines, seeded = reset(kube)
        with self.assertRaises(demo_reset.Refused):
            r.run()
        self.assertEqual(seeded, [])
        self.assertIn('FAILED ops agent: restarted (in-memory proposals cleared)', lines)

    def test_release_render_and_reset_inventory_use_the_real_cli(self):
        import lifecycle
        project = 'render-fixture'
        options = {'project_id': project, 'control_plane_cidr': '172.16.0.16/28',
                   'gateway_gsa': 'fixture-gateway@' + project + '.iam.gserviceaccount.com',
                   'redactor_gsa': 'fixture-redactor@' + project + '.iam.gserviceaccount.com'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(lifecycle, 'STATE', Path(tmp)), \
                patch.object(lifecycle, 'KUBECTL', shutil.which('kubectl') or 'kubectl'):
            rendered = lifecycle.render_release(options)
            selected = json.loads((Path(tmp) / 'release-rc1.lock.json').read_text())
        fault, required = demo_reset.declared_state(rendered)
        docs = list(yaml.safe_load_all(rendered))
        self.assertEqual(yaml.safe_load(fault)['metadata']['name'], 'fault-demo')
        self.assertTrue({('deployment', 'platform', 'gateway-boundary'),
                         ('deployment', 'apps', 'financial-frontdoor'),
                         ('deployment', 'ops', 'ops-executor'),
                         ('statefulset', 'platform', 'postgres')} <= set(required))
        self.assertTrue({('deployment', 'agent-financial', 'agent-u' + str(i)) for i in range(1, 4)} <= set(required))
        self.assertEqual(selected['runtime_contract'], 'trusted-boundaries-v2')
        self.assertTrue(all(c['image'].endswith(tuple(selected['images'].values())) for doc in docs
                            if doc['kind'] == 'Deployment' for c in doc['spec']['template']['spec']['containers']))
        # A missing current boundary must stop reset before any mutation, rather than checking three historical names.
        kube = Kube(fail='get deployment ops-executor')
        r = demo_reset.Reset(kubectl=kube, nodes=lambda: 1, declared=(fault, required),
                             seed=lambda: self.fail('must not seed'), ask=lambda _: self.fail('must not prompt'))
        with self.assertRaisesRegex(demo_reset.Refused, 'ops/ops-executor'):
            r.run()
        self.assertTrue(all('get' in args for args, _ in kube.calls))

    def test_invalid_fault_declaration_refuses(self):
        for text in ('', 'kind: Deployment\nmetadata: {name: fault-demo, namespace: apps}\nspec: {replicas: 1}\n'):
            with self.subTest(text=text), self.assertRaises(demo_reset.Refused):
                demo_reset.declared_state(text)

    def test_partial_or_stale_rollout_is_not_ready(self):
        for output in ('2 1 1 3 3', '1 1 1 3 2', '0 0 0 3 3', 'unreadable', '1 1'):
            r, _, _ = reset(lambda *args, **kwargs: (0, output))
            with self.subTest(output=output):
                self.assertFalse(r.ready('deployment', 'apps', 'app'))


if __name__ == '__main__':
    unittest.main()
