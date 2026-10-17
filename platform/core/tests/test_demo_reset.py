"""make demo-reset (offline, fake kubectl): refuses a down or unready platform, asks first, never touches a Secret."""
from pathlib import Path
import sys
import unittest

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
            return (0, '1') if self.ready else (0, '')
        if 'exec' in args:
            return 0, 'redactor warm-up: ok\n'
        return 0, ''


def reset(kube, *, nodes=1, answer='yes'):
    lines, seeded = [], []
    r = demo_reset.Reset(kubectl=kube, nodes=lambda: nodes, render_fault_demo=lambda: 'kind: Deployment\n', seed=lambda: seeded.append(1),
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

    def test_a_refused_warm_up_is_reported_with_the_fallback_and_nothing_else_is_tried(self):
        kube = Kube(fail='exec')
        r, lines, seeded = reset(kube)
        self.assertEqual(r.run(), 0)  # the reset itself completed
        self.assertIn('FAILED redactor warm-up (kubectl exec was refused or failed; nothing was bypassed).', lines)
        self.assertTrue(any('ask one non-personal question in the console' in l for l in lines))
        self.assertEqual(sum('exec' in c[0] for c in kube.calls), 1)  # one attempt, no other route

    def test_a_failed_step_stops(self):
        kube = Kube(fail='rollout restart')
        r, lines, seeded = reset(kube)
        with self.assertRaises(demo_reset.Refused):
            r.run()
        self.assertEqual(seeded, [])
        self.assertIn('FAILED ops agent: restarted (in-memory proposals cleared)', lines)


if __name__ == '__main__':
    unittest.main()
