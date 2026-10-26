"""An existing immutable sha-<S> tag is verified, never rebuilt or retagged; no registry/cloud/network calls."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'platform/core/src'))
spec = importlib.util.spec_from_file_location('existing_image_tag', ROOT / 'scripts/existing-image-tag.py')
existing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(existing)

from agent_platform.release_verify import IDENTITY, ISSUER, Verifier  # noqa: E402

PROJECT, SOURCE = 'example-project', 'd' * 40
DIGEST = 'sha256:' + 'b' * 64
REPO = 'us-east1-docker.pkg.dev/' + PROJECT + '/sdp-evaluation-images/platform-guide'
REF = REPO + '@' + DIGEST
BUILDER = 'moby/buildkit@sha256:99368f3e46177c6405b9740e4461d91cee004128daeecca78d4ceac50ec1da5c'
PREDICATE = {'schema': 2, 'source_commit': SOURCE, 'image': 'platform-guide',
             'build_environment': 'github-hosted:ubuntu-24.04', 'git_archive_sha256': 'a' * 64,
             'input_fingerprint': 'c' * 64, 'materials': sorted(['node:24@sha256:' + 'f' * 64, BUILDER]),
             'platform': 'linux/amd64', 'builder': BUILDER}


class Response:
    def __init__(self, status=200, digest=DIGEST):
        self.status, self.headers = status, {'Docker-Content-Digest': digest}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def registry(answer):
    seen = []

    def open_url(request, timeout):
        seen.append(request)
        if isinstance(answer, int):
            raise urllib.error.HTTPError(request.full_url, answer, 'status', {}, io.BytesIO())
        return answer
    return open_url, seen


def lookup(answer):
    open_url, seen = registry(answer)
    return existing.lookup('us-east1-docker.pkg.dev', PROJECT, 'sdp-evaluation-images', 'platform-guide', SOURCE,
                           'short-lived', open_url=open_url), seen


class Cosign:
    """cosign verify / verify-attestation with the observed JSON output shapes; flags select a failure."""

    def __init__(self, *, signed=True, predicate=PREDICATE, workflow_sha=SOURCE):
        self.signed, self.predicate, self.workflow_sha = signed, predicate, workflow_sha
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if '--certificate-github-workflow-sha=' + self.workflow_sha not in args:
            return 1, ''
        if ('--certificate-identity=' + IDENTITY not in args
                or '--certificate-oidc-issuer=' + ISSUER not in args or args[2] != REF):
            return 1, ''
        if args[1] == 'verify':
            if not self.signed:
                return 1, ''
            return 0, json.dumps([{'critical': {'identity': {'docker-reference': REPO},
                                                'image': {'docker-manifest-digest': DIGEST},
                                                'type': 'cosign container image signature'},
                                   'optional': {'githubWorkflowSha': self.workflow_sha}}])
        if args[1] == 'verify-attestation':
            if self.predicate is None:
                return 1, ''
            statement = {'_type': 'https://in-toto.io/Statement/v0.1',
                         'predicateType': 'https://cosign.sigstore.dev/attestation/v1',
                         'subject': [{'name': REPO, 'digest': {'sha256': 'b' * 64}}],
                         'predicate': {'Data': json.dumps(self.predicate), 'Timestamp': '2026-10-26T18:00:00Z'}}
            return 0, json.dumps({'payloadType': 'application/vnd.in-toto+json',
                                  'payload': base64.b64encode(json.dumps(statement).encode()).decode(),
                                  'signatures': [{'keyid': '', 'sig': 'MEUC'}]})
        return 1, ''


def verify(cosign):
    existing.verify(REF, PREDICATE, Verifier(PROJECT, SOURCE, cosign))


class TagAbsent(unittest.TestCase):
    def test_unknown_tag_or_image_means_build(self):
        digest, seen = lookup(404)
        self.assertIsNone(digest)
        request = seen[0]
        self.assertEqual(request.get_method(), 'HEAD')
        self.assertEqual(request.full_url, 'https://us-east1-docker.pkg.dev/v2/' + PROJECT
                         + '/sdp-evaluation-images/platform-guide/manifests/sha-' + SOURCE)
        self.assertEqual(request.get_header('Authorization'),
                         'Basic ' + base64.b64encode(b'oauth2accesstoken:short-lived').decode())

    def test_any_other_registry_answer_fails_closed(self):
        for answer in (401, 403, 500, Response(digest=''), Response(digest='sha256:short'), Response(status=202)):
            with self.subTest(answer=answer):
                with self.assertRaises(RuntimeError):
                    lookup(answer)

    def test_invalid_lookup_input_is_rejected_before_any_request(self):
        open_url, seen = registry(Response())
        for args in (('Bad_Project', 'platform-guide', SOURCE, 't'), (PROJECT, '../x', SOURCE, 't'),
                     (PROJECT, 'platform-guide', 'main', 't'), (PROJECT, 'platform-guide', SOURCE, '')):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    existing.lookup('us-east1-docker.pkg.dev', args[0], 'sdp-evaluation-images', args[1], args[2],
                                    args[3], open_url=open_url)
        self.assertEqual(seen, [])


class TagExistsAndVerifies(unittest.TestCase):
    def test_existing_digest_is_returned(self):
        digest, _ = lookup(Response())
        self.assertEqual(digest, DIGEST)

    def test_signature_at_s_and_predicate_for_s_verify(self):
        cosign = Cosign()
        verify(cosign)
        self.assertEqual([call[1] for call in cosign.calls], ['verify', 'verify-attestation'])
        self.assertFalse(any(call[1] in ('sign', 'attest', 'copy', 'tag') for call in cosign.calls))


class TagExistsAndFailsVerification(unittest.TestCase):
    def test_unsigned_subject_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'keyless signature'):
            verify(Cosign(signed=False))

    def test_signature_from_another_workflow_revision_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'keyless signature'):
            verify(Cosign(workflow_sha='e' * 40))

    def test_missing_or_different_predicate_fails(self):
        changed = dict(PREDICATE, git_archive_sha256='0' * 64)
        other_source = dict(PREDICATE, source_commit='e' * 40)
        cases = {'missing': None, 'other archive': changed, 'other source': other_source,
                 'other materials': dict(PREDICATE, materials=[BUILDER])}
        for case, predicate in cases.items():
            with self.subTest(case=case):
                with self.assertRaisesRegex(RuntimeError, 'predicate for S'):
                    verify(Cosign(predicate=predicate))


class WorkflowContract(unittest.TestCase):
    def setUp(self):
        import yaml
        self.image = yaml.safe_load((ROOT / '.github/workflows/agent-platform-images.yml').read_text())['jobs']['image']
        self.steps = self.image['steps']

    def step(self, **match):
        return next(s for s in self.steps if all(s.get(k) == v for k, v in match.items()))

    def test_forced_matrix_does_not_fail_fast(self):
        self.assertEqual(self.image['strategy']['fail-fast'], "${{ github.event_name != 'workflow_dispatch' }}")
        self.assertEqual(self.image['strategy']['max-parallel'], 1)

    def test_lookup_precedes_build_without_exporting_credentials(self):
        lookup_auth, found = self.step(id='lookup-auth'), self.step(id='existing')
        self.assertFalse(lookup_auth['with']['create_credentials_file'])
        self.assertFalse(lookup_auth['with']['export_environment_variables'])
        self.assertIn('scripts/existing-image-tag.py lookup', found['run'])
        build = self.step(name='Build exact S on the hosted runner (no cloud credentials)')
        order = [self.steps.index(s) for s in (lookup_auth, found, build, self.step(id='auth'))]
        self.assertEqual(order, sorted(order))
        for name in ('Build exact S on the hosted runner (no cloud credentials)',
                     'Trivy (all severities and KEV; fail-closed) and SBOM'):
            self.assertEqual(self.step(name=name)['if'], "steps.existing.outputs.digest == ''")

    def test_existing_subject_is_gated_and_verified_never_pushed_retagged_or_signed(self):
        publish = self.step(id='publish')
        self.assertEqual(publish['env']['EXISTING'], '${{ steps.existing.outputs.digest }}')
        text = publish['run']
        first_existing = text.index('if [[ -n "$EXISTING" ]]; then')
        first_else = text.index('\nelse\n', first_existing)
        reuse = text[first_existing:first_else]
        second_existing = text.index('if [[ -n "$EXISTING" ]]; then', first_else)
        verify_only = text[second_existing:text.index('\nelse\n', second_existing)]
        for forbidden in ('docker push', 'docker tag', 'cosign" sign', 'cosign" attest', 'imagetools create', 'crane'):
            self.assertNotIn(forbidden, reuse + verify_only)
        for gate in ('reviewed-image-exception-gate.py "$RUNNER_TEMP/trivy.json" "$ref"', 'syft" "registry:$ref"'):
            self.assertIn(gate, reuse)
        self.assertIn('scripts/existing-image-tag.py verify', verify_only)
        common = text[first_else:second_existing]
        for gate in ('trivy-full.json', 'kev-release-gate.py', 'image-provenance.py --plan'):
            self.assertIn(gate, common)
        self.assertIn('attestations sign-and-create', text[second_existing:])
        evidence = self.steps[-1]['with']['path']
        self.assertIn('subject-origin.txt', evidence)


if __name__ == '__main__':
    unittest.main()
