"""make demo-check (offline, fake gcloud/kubectl): PASS/FAIL lines, never a secret value or the project ID."""
import base64
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'clouds/gke'))
import demo_check  # noqa: E402

PROJECT = 'demo-project-123456'
DIGEST = 'b' * 64
SECRET_KEY = 'sk-' + 'Z' * 40


def secret(entry, value):
    return json.dumps({'data': {entry: base64.b64encode(json.dumps(value).encode()).decode()}})


class Fake:
    """Answers like gcloud/kubectl would; every answer embeds the project ID or a key to prove nothing leaks."""

    def __init__(self, *, hello=False, signed=True, attested=True, secrets_present=True, api=True):
        self.hello, self.signed, self.attested, self.present, self.api = hello, signed, attested, secrets_present, api
        self.calls = []

    def __call__(self, args, input=None):
        self.calls.append(args)
        a = ' '.join(map(str, args))
        if 'auth list' in a:
            return 0, 'owner@' + PROJECT + '.example\n'
        if 'print-access-token' in a:
            return 0, 'ya29.' + 'x' * 40 + '\n'
        if 'clusters describe' in a:
            return 0, json.dumps({'status': 'RUNNING', 'nodePools': [{'name': 'work'}], 'selfLink': 'projects/' + PROJECT})
        if 'instance-groups' in a:
            return 0, '0\n'
        if 'tags list' in a:
            return 0, ('projects/%s/locations/us-east1/repositories/r/packages/x/tags/sha256-%s.sig\n' % (PROJECT, DIGEST)) if self.signed else ''
        if 'attestations list' in a:
            return 0, ('projects/%s/notes/n/occurrences/1\n' % PROJECT) if self.attested else ''
        if not self.api and args[0] != 'gcloud':
            return 1, ''
        if 'get namespace platform' in a:
            return 0, 'namespace/platform\n'
        if 'get namespace agent-hello' in a:
            return 0, 'namespace/agent-hello\n' if self.hello else ''
        if 'get networkpolicy' in a:
            return 0, ('networkpolicy/' + args[-4] + '\n') if self.hello else ''
        if 'secret bootstrap -o json' in a:
            return 0, secret('bootstrap.json', {'virtual_keys': [{'alias': 'agent-financial', 'key': SECRET_KEY}] +
                                                ([{'alias': 'agent-hello', 'key': SECRET_KEY}] if self.hello else [])})
        if 'secret redactor -o json' in a:
            return 0, secret('clients.json', dict({'app': SECRET_KEY}, **({'agent-hello': SECRET_KEY} if self.hello else {})))
        if 'get secret' in a:
            return 0, 'secret/x\n' if self.present else ''
        return 1, ''


def check(fake, images=None):
    lines = []
    images = images or {'registry': 'us-east1-docker.pkg.dev/PROJECT_ID/repo/', 'images': {'app': 'agent-platform-app@sha256:' + DIGEST}}
    code = demo_check.Checker(PROJECT, run=fake, images=images, agents=('financial',), out=lines.append).all()
    return code, lines


class DemoCheck(unittest.TestCase):
    def test_all_pass(self):
        code, lines = check(Fake())
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[-1], 'all checks passed')
        self.assertTrue(all(l.startswith('PASS  ') for l in lines[:-1]))

    def test_never_prints_the_project_id_an_account_or_a_secret(self):
        for fake in (Fake(), Fake(hello=True, signed=False, attested=False, secrets_present=False), Fake(api=False)):
            _, lines = check(fake)
            text = '\n'.join(lines)
            for leak in (PROJECT, SECRET_KEY, 'ya29.', 'owner@', 'projects/'):
                self.assertNotIn(leak, text)

    def test_pending_ci_and_missing_signature_or_attestation_fail(self):
        images = {'registry': 'r/PROJECT_ID/', 'images': {'platform-guide': 'PENDING_CI'}}
        code, lines = check(Fake(), images)
        self.assertEqual(code, 1)
        self.assertIn('FAIL  image platform-guide pinned  (not a digest: PENDING_CI)', lines)
        _, lines = check(Fake(signed=False, attested=False))
        self.assertTrue(any(l.startswith('FAIL  image app signed') for l in lines))
        self.assertTrue(any(l.startswith('FAIL  image app attested') for l in lines))

    def test_hello_leftovers_fail_by_name_only(self):
        code, lines = check(Fake(hello=True))
        self.assertEqual(code, 1)
        failed = [l for l in lines if l.startswith('FAIL')]
        self.assertEqual(len(failed), 5)  # namespace, two NetworkPolicies, two key aliases
        self.assertIn('still present: run --retire-agent hello', '\n'.join(failed))

    def test_missing_secrets_and_no_cluster_access(self):
        code, lines = check(Fake(secrets_present=False))
        self.assertIn('FAIL  secret agent-financial/agent exists', lines)
        code, lines = check(Fake(api=False))
        self.assertIn('FAIL  secrets and hello leftovers  (skipped: no cluster API access)', lines)

    def test_checks_the_images_make_up_deploys(self):
        lock = json.loads((demo_check.HERE / 'release-rc1.lock.json').read_text())
        checker = demo_check.Checker(PROJECT, run=Fake(), out=[].append)
        self.assertEqual(checker.images, lock)
        self.assertEqual(lock['runtime_contract'], 'trusted-boundaries-v2')

    def test_read_only_commands_only(self):
        fake = Fake(hello=True)
        check(fake)
        writes = {'apply', 'delete', 'patch', 'create', 'scale', 'edit', 'replace', 'resize', 'exec', 'sign-and-create', 'set'}
        for args in fake.calls:
            self.assertFalse(writes & set(map(str, args)), args)


if __name__ == '__main__':
    unittest.main()
