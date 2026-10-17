"""make passphrase-check / make passphrase (offline, fake kubectl): only operator_secret_scrypt changes, nothing secret is
printed, a non-terminal stdin and a mismatched or short entry are refused before anything is applied."""
import base64
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'clouds/gke'))
import passphrase  # noqa: E402

OLD = 'correct horse battery staple'
NEW = 'a brand new passphrase 42'
SALT = bytes(range(16))


def app_json():
    return json.dumps({'issuer_private_key': '-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n',
                       'tenant_directory': {'fixture-a': {'name': 'Fixture A ✓'}}, 'client_keys': {'financial': 'sk-111'},
                       'redactor_key': 'r' * 64, 'approver_private_key': 'p' * 64,
                       'operator_secret_scrypt': {'salt': SALT.hex(), 'hash': passphrase.scrypt(OLD, SALT)},
                       'ops_api_key': 'o' * 64, 'users': {'alpha': {'subject': 's', 'tenant': 'fixture-a'}}})


def live_secret(text=None):
    return {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
            'metadata': {'name': 'app', 'namespace': 'apps', 'resourceVersion': '7', 'uid': 'u',
                         'labels': {'app.kubernetes.io/part-of': 'agent-platform'},
                         'annotations': {passphrase.LAST_APPLIED: '{"data":{"app.json":"..."}}'}},
            'data': {'app.json': base64.b64encode((text or app_json()).encode()).decode(), 'other': 'b3RoZXI='}}


class Kube:
    def __init__(self, replicas='1', fail=None, secret=None):
        self.replicas, self.fail, self.calls = replicas, fail, []
        self.secret = secret or live_secret()

    def __call__(self, *args, input=None):
        self.calls.append((args, input))
        a = ' '.join(args)
        if self.fail and self.fail in a:
            return 1, ''
        if 'get secret' in a:
            return 0, json.dumps(self.secret)
        if 'status.replicas' in a:
            return 0, self.replicas
        return 0, ''

    def applied(self):
        return [json.loads(i) for args, i in self.calls if args[:1] == ('apply',)]


def tool(kube, answers, tty=True):
    lines, answers = [], list(answers)
    return passphrase.Passphrase(kubectl=kube, isatty=lambda: tty, ask=lambda prompt: answers.pop(0), out=lines.append), lines


class Check(unittest.TestCase):
    def test_match_true_and_false_and_only_that_is_printed(self):
        for typed, expected in ((OLD, True), (OLD + ' ', False), ('wrong passphrase!', False)):
            kube = Kube()
            t, lines = tool(kube, [typed])
            self.assertEqual(t.check(), 0)
            self.assertEqual(lines, [json.dumps({'match': expected})])
            self.assertEqual(kube.applied(), [])
            self.assertFalse([c for c in kube.calls if c[0][:1] != ('-n',) or 'get' not in c[0]])  # read-only


class Replace(unittest.TestCase):
    def test_only_the_scrypt_field_changes_byte_for_byte(self):
        kube = Kube()
        t, lines = tool(kube, [NEW, NEW])
        self.assertEqual(t.replace(), 0)
        [manifest] = kube.applied()
        old_text, new_text = app_json(), base64.b64decode(manifest['data']['app.json']).decode()
        new_value = json.loads(new_text)['operator_secret_scrypt']
        old_value = json.loads(old_text)['operator_secret_scrypt']
        self.assertEqual(new_text.replace(json.dumps(new_value), json.dumps(old_value), 1), old_text)
        self.assertEqual(manifest['data']['other'], 'b3RoZXI=')
        self.assertEqual(set(manifest['data']), {'app.json', 'other'})
        self.assertEqual(manifest['metadata'], {'name': 'app', 'namespace': 'apps', 'labels': {'app.kubernetes.io/part-of': 'agent-platform'}})
        self.assertEqual(manifest['type'], 'Opaque')
        self.assertNotEqual(new_value['salt'], SALT.hex())
        self.assertEqual(len(bytes.fromhex(new_value['salt'])), 16)
        self.assertTrue(passphrase.matches(NEW, new_value))
        self.assertFalse(passphrase.matches(OLD, new_value))
        self.assertEqual(lines, [json.dumps({'result': 'PASSPHRASE_REPLACED', 'values_printed': False})])

    def test_rolls_out_the_front_door_only_when_it_has_pods(self):
        for replicas, rolled in (('1', True), ('0', False), ('', False)):
            kube = Kube(replicas=replicas)
            t, _ = tool(kube, [NEW, NEW])
            t.replace()
            rollouts = [c[0] for c in kube.calls if 'rollout' in c[0]]
            self.assertEqual(rollouts, [('-n', 'apps', 'rollout', 'restart', 'deployment/app'),
                                        ('-n', 'apps', 'rollout', 'status', 'deployment/app', '--timeout=300s')] if rolled else [])

    def test_nothing_secret_is_printed(self):
        kube = Kube()
        t, lines = tool(kube, [NEW, NEW])
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            t.replace()
        new_value = json.loads(base64.b64decode(kube.applied()[0]['data']['app.json']))['operator_secret_scrypt']
        printed = '\n'.join(lines) + stdout.getvalue() + stderr.getvalue()
        for value in (NEW, OLD, new_value['salt'], new_value['hash'], SALT.hex(), 'p' * 64, 'r' * 64, 'sk-111', 'BEGIN PRIVATE KEY'):
            self.assertNotIn(value, printed)

    def test_non_tty_is_refused_before_anything_is_read(self):
        for method in ('check', 'replace'):
            kube = Kube()
            t, lines = tool(kube, [NEW, NEW], tty=False)
            with self.assertRaises(passphrase.Refused):
                getattr(t, method)()
            self.assertEqual(kube.calls, [])
            self.assertEqual(lines, [])

    def test_mismatch_short_or_padded_entries_are_refused_and_nothing_is_applied(self):
        for answers in ([NEW, NEW + 'x'], ['short-pass', 'short-pass'], [' ' + NEW, ' ' + NEW]):
            kube = Kube()
            t, lines = tool(kube, answers)
            with self.assertRaises(passphrase.Refused) as refused:
                t.replace()
            self.assertEqual(kube.calls, [])
            self.assertNotIn(answers[0].strip(), str(refused.exception.code))

    def test_failed_apply_reports_unchanged_and_never_rolls_out(self):
        kube = Kube(fail='apply')
        t, lines = tool(kube, [NEW, NEW])
        with self.assertRaises(passphrase.Refused):
            t.replace()
        self.assertFalse([c for c in kube.calls if 'rollout' in c[0]])
        self.assertEqual(lines, [])

    def test_unstable_json_is_refused_rather_than_reformatted(self):
        pretty = json.dumps(json.loads(app_json()), indent=1)  # not what make secrets writes
        kube = Kube(secret=live_secret(pretty))
        t, _ = tool(kube, [NEW, NEW])
        with self.assertRaises(passphrase.Refused):
            t.replace()
        self.assertEqual(kube.applied(), [])


if __name__ == '__main__':
    unittest.main()
