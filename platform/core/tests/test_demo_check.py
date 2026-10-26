"""Readiness uses the current full render; attestation fixtures carry real P-256 signatures."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'clouds/gke'))
import demo_check  # noqa: E402
import lifecycle  # noqa: E402
from agent_platform.release_verify import IDENTITY, ISSUER, Verifier  # noqa: E402
from test_render_fields import render  # noqa: E402

PROJECT, SOURCE = 'render-fixture', 'd' * 40
KEY = ec.generate_private_key(ec.SECP256R1())
PEM = KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
KEY_ID = 'projects/' + PROJECT + '/locations/us-east1/keyRings/agent-platform/cryptoKeys/binauthz-attestor/cryptoKeyVersions/1'
NOTE = 'projects/' + PROJECT + '/notes/agent-platform-attestor'


def signed_occurrence(ref, *, key=KEY):
    repo, digest = ref.rsplit('@', 1)
    raw = json.dumps({'critical': {'identity': {'docker-reference': repo},
        'image': {'docker-manifest-digest': digest}, 'type': 'Google cloud binauthz container signature'}}).encode()
    return {'kind': 'ATTESTATION', 'resourceUri': 'https://' + ref, 'noteName': NOTE,
            'attestation': {'serializedPayload': base64.b64encode(raw).decode(), 'signatures': [
                {'publicKeyId': KEY_ID, 'signature': base64.b64encode(key.sign(raw, ec.ECDSA(hashes.SHA256()))).decode()}]}}


def live_items(docs):
    groups = {}
    for source in docs:
        if source['kind'] not in ('Deployment', 'StatefulSet'):
            continue
        d = deepcopy(source)
        namespace, name = d['metadata']['namespace'], d['metadata']['name']
        uid = namespace + '-' + name
        d['metadata'].update(uid=uid, generation=2)
        count = d['spec'].get('replicas', 1)
        d['status'] = {k: count for k in ('replicas', 'updatedReplicas', 'readyReplicas', 'availableReplicas')}
        d['status'].update(observedGeneration=2, currentRevision='r1', updateRevision='r1')
        items = groups.setdefault(namespace, [])
        items.append(d)
        parent = uid
        if d['kind'] == 'Deployment':
            parent = uid + '-rs'
            items.append({'kind': 'ReplicaSet', 'metadata': {'name': parent, 'uid': parent,
                'ownerReferences': [{'uid': uid, 'controller': True}]}})
        for i in range(count):
            items.append({'kind': 'Pod', 'metadata': {'name': uid + '-' + str(i),
                'ownerReferences': [{'uid': parent, 'controller': True}]},
                'spec': deepcopy(d['spec']['template']['spec']),
                'status': {'phase': 'Running', 'conditions': [{'type': 'Ready', 'status': 'True'}],
                           'containerStatuses': [{'name': c['name'], 'ready': True, 'state': {'running': {}},
                               'imageID': 'docker-pullable://' + c['image']} for c in d['spec']['template']['spec']['containers']]}})
    return groups


class Fake:
    def __init__(self, docs=(), *, signed=True, attested=True, capacity=1, secrets_present=True, api=True):
        self.signed, self.attested, self.capacity = signed, attested, capacity
        self.present, self.api, self.calls = secrets_present, api, []
        self.groups = live_items(docs)
        self.authority = {'name': 'projects/' + PROJECT + '/attestors/agent-platform-ci',
            'userOwnedGrafeasNote': {'noteReference': NOTE, 'publicKeys': [{'id': KEY_ID,
                'pkixPublicKey': {'publicKeyPem': PEM, 'signatureAlgorithm': 'EC_SIGN_P256_SHA256'}}]}}
        self.kms = {'name': KEY_ID, 'pem': PEM, 'algorithm': 'EC_SIGN_P256_SHA256'}
        self.change_occurrence = lambda value: value

    def __call__(self, args, input=None):
        args = list(map(str, args))
        self.calls.append(args)
        if args[0] == 'openssl':
            return demo_check.subprocess_runner(args, input=input)
        if args[0] == 'cosign':
            if not self.signed or '--certificate-github-workflow-sha=' + SOURCE not in args:
                return 1, ''
            repo, digest = args[2].rsplit('@', 1)
            return 0, json.dumps([{'critical': {'identity': {'docker-reference': repo},
                'image': {'docker-manifest-digest': digest}, 'type': 'cosign container image signature'}}])
        a = ' '.join(args)
        if 'auth list' in a:
            return 0, 'owner@' + PROJECT + '.example'
        if 'clusters describe' in a:
            return 0, json.dumps({'status': 'RUNNING', 'nodePools': [{'name': 'work'}]})
        if 'instance-groups' in a:
            return 0, str(self.capacity)
        if 'attestors describe' in a:
            return 0, json.dumps(self.authority)
        if 'get-public-key' in args:
            return 0, json.dumps(self.kms)
        if 'attestations list' in a:
            ref = args[args.index('--artifact-url') + 1]
            return 0, json.dumps([self.change_occurrence(signed_occurrence(ref))] if self.attested else [])
        if not self.api:
            return 1, ''
        if 'get nodes' in a:
            return 0, json.dumps({'items': [{'spec': {}, 'metadata': {}, 'status': {
                'conditions': [{'type': 'Ready', 'status': 'True'}]}}] if self.capacity else []})
        if 'deployments,statefulsets,replicasets,pods' in args:
            return 0, json.dumps({'items': self.groups.get(args[args.index('-n') + 1], [])})
        if 'get secret' in a:
            return 0, 'secret/' + args[args.index('secret') + 1] if self.present else ''
        return 1, ''


class DemoCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = json.loads((demo_check.HERE / 'release-rc1.lock.json').read_text())
        cls.images['source_commit'] = SOURCE
        cls.images['registry'] = cls.images['registry'].replace('PROJECT_ID', PROJECT)
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / 'lock.json'
            lock.write_text(json.dumps(cls.images))
            raw, _ = render.render(SimpleNamespace(images_lock=lock, project_id=PROJECT,
                control_plane_cidr='172.16.0.16/28', gateway_gsa='fixture-gateway@' + PROJECT + '.iam.gserviceaccount.com',
                redactor_gsa='fixture-redactor@' + PROJECT + '.iam.gserviceaccount.com',
                kubectl=str(demo_check.REPO / '.cache/envtest-v1.35.0/kubectl')))
        cls.docs = list(yaml.safe_load_all(raw))

    def check(self, fake=None, docs=None, images=None):
        lines = []
        fake = fake or Fake(self.docs)
        code = demo_check.Checker(PROJECT, run=fake, docs=self.docs if docs is None else docs,
            images=self.images if images is None else images, out=lines.append).all()
        return code, lines

    def test_current_full_render_all_required_workloads_and_real_attestations_pass(self):
        fake = Fake(self.docs)
        code, lines = self.check(fake)
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[-1], 'all checks passed')
        self.assertTrue(all(l.startswith('PASS  ') for l in lines[:-1]))
        for name in ('gateway-boundary', 'financial-frontdoor', 'ops-executor', 'agent-u1', 'agent-u2', 'agent-u3'):
            self.assertIn('/' + name + ' ready on selected images', '\n'.join(lines))
        for args in fake.calls:
            if args[0] == 'cosign':
                self.assertIn('--certificate-identity=' + IDENTITY, args)
                self.assertIn('--certificate-oidc-issuer=' + ISSUER, args)
                self.assertIn('--certificate-github-workflow-sha=' + SOURCE, args)
                self.assertFalse(any('ignore' in a or 'regexp' in a for a in args))

    def test_zero_nodes_empty_inventory_missing_worker_and_api_failure_are_not_ready(self):
        for fake, docs in ((Fake(self.docs, capacity=0), self.docs), (Fake(), []),
                           (Fake(self.docs, api=False), self.docs)):
            self.assertEqual(self.check(fake, docs=docs)[0], 1)
        fake = Fake(self.docs)
        fake.groups['agent-financial'] = [d for d in fake.groups['agent-financial']
                                          if not (d['kind'] == 'Deployment' and d['metadata']['name'] == 'agent-u2')]
        self.assertEqual(self.check(fake)[0], 1)

    def test_apply_staging_preserves_the_final_declared_ops_target_and_stops_only_the_apply_copy(self):
        staged = lifecycle.staged_documents(self.docs)
        targets = lifecycle.activation_targets(self.docs)
        self.assertEqual([(d['metadata']['namespace'], d['metadata']['name'], d['spec']['replicas']) for d in targets],
                         [('ops', 'ops-agent', 1)])
        self.assertEqual(next(d for d in staged if d['kind'] == 'Deployment' and d['metadata']['name'] == 'ops-agent')['spec']['replicas'], 0)
        self.assertEqual(next(d for d in self.docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'ops-agent')['spec']['replicas'], 1)
        fake = Fake(staged)
        self.assertEqual(self.check(fake)[0], 1)
        self.assertIn('workload apps/fault-demo stopped as declared', '\n'.join(self.check()[1]))

    def test_make_up_applies_ops_stopped_then_activates_only_after_all_required_rollouts(self):
        calls = []
        def kubectl(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout='secret/present')
        with patch.object(lifecycle, 'resize'), patch.object(lifecycle, 'kubeconfig'), \
                patch.object(lifecycle, 'scale_staged_to_zero'), patch.object(lifecycle, 'finance_tools'), \
                patch.object(lifecycle, 'render_release', return_value=yaml.safe_dump_all(self.docs)), \
                patch.object(lifecycle, 'kubectl', side_effect=kubectl), \
                patch.object(lifecycle, 'run', return_value=SimpleNamespace(stdout='{"platform_keys_changed":false}')), \
                patch('builtins.print'):
            lifecycle.up()
        applied = [d for args, kw in calls if args[0] == 'apply' for d in yaml.safe_load_all(kw['input']) if d]
        ops = next(d for d in applied if d['kind'] == 'Deployment' and d['metadata']['name'] == 'ops-agent')
        self.assertEqual(ops['spec']['replicas'], 0)
        activation = next(i for i, (args, _) in enumerate(calls) if args == ('-n', 'ops', 'scale', 'deployment/ops-agent', '--replicas=1'))
        for doc in self.docs:
            if doc['kind'] != 'Deployment' or not doc['spec'].get('replicas', 1) or doc['metadata']['name'] == 'ops-agent':
                continue
            expected = ('-n', doc['metadata']['namespace'], 'rollout', 'status', 'deployment/' + doc['metadata']['name'], '--timeout=300s')
            self.assertLess(next(i for i, (args, _) in enumerate(calls) if args == expected), activation)

    def test_ready_counts_cannot_hide_wrong_desired_or_running_images_or_stale_generation(self):
        for target in ('desired-image', 'pod-image', 'running-digest', 'not-ready', 'stale-generation', 'foreign-pod', 'duplicate-status'):
            with self.subTest(target=target):
                fake = Fake(self.docs)
                docs = fake.groups['agent-financial']
                d = next(d for d in docs if d['kind'] == 'Deployment')
                pod = next(d for d in docs if d['kind'] == 'Pod')
                if target == 'desired-image': d['spec']['template']['spec']['containers'][0]['image'] = 'other@sha256:' + 'e' * 64
                if target == 'pod-image': pod['spec']['containers'][0]['image'] = 'other@sha256:' + 'e' * 64
                if target == 'running-digest': pod['status']['containerStatuses'][0]['imageID'] = 'sha256:' + 'e' * 64
                if target == 'not-ready': pod['status']['containerStatuses'][0]['ready'] = False
                if target == 'stale-generation': d['status']['observedGeneration'] = 1
                if target == 'foreign-pod': pod['metadata']['ownerReferences'][0]['uid'] = 'foreign'
                if target == 'duplicate-status': pod['status']['containerStatuses'].append(deepcopy(pod['status']['containerStatuses'][0]))
                self.assertEqual(self.check(fake)[0], 1)

    def test_invalid_signature_attestation_or_source_prevents_readiness(self):
        for fake in (Fake(self.docs, signed=False), Fake(self.docs, attested=False)):
            self.assertEqual(self.check(fake)[0], 1)
        for source in (None, 'main', 'e' * 39, 'e' * 40):
            images = dict(self.images, source_commit=source)
            self.assertEqual(self.check(images=images)[0], 1)
        images = deepcopy(self.images)
        images['images']['app'] = 'PENDING_CI'
        self.assertEqual(self.check(images=images)[0], 1)

    def test_runtime_digest_forms_match_only_the_exact_pinned_subject(self):
        digest, other = 'sha256:' + 'b' * 64, 'sha256:' + 'e' * 64
        for image_id in (digest, 'containerd://' + digest, 'docker://repo/app@' + digest, 'docker-pullable://repo/app@' + digest):
            self.assertTrue(demo_check.image_matches(image_id, 'repo/app@' + digest))
            self.assertFalse(demo_check.image_matches(image_id, 'repo/app@' + other))
        self.assertFalse(demo_check.image_matches('repo/app:latest', 'repo/app:latest'))

    def test_required_secrets_follow_rendered_references_without_reading_values(self):
        names = demo_check.required_secrets(self.docs)
        for item in (('platform', 'gateway-boundary'), ('apps', 'financial-frontdoor'), ('ops', 'ops-executor')):
            self.assertIn(item, names)
        self.assertEqual(self.check(Fake(self.docs, secrets_present=False))[0], 1)
        fake = Fake(self.docs)
        self.check(fake)
        for args in fake.calls:
            if 'secret' in args:
                self.assertEqual(args[-2:], ['-o', 'name'])

    def test_output_is_closed_and_cloud_operations_are_read_only(self):
        fake = Fake(self.docs, signed=False, secrets_present=False)
        _, lines = self.check(fake)
        text = '\n'.join(lines)
        for leak in (PROJECT, 'owner@', 'projects/', 'ya29.', 'BEGIN PUBLIC KEY', '.iam.gserviceaccount.com'):
            self.assertNotIn(leak, text)
        for args in fake.calls:
            self.assertFalse({'apply', 'delete', 'patch', 'create', 'scale', 'edit', 'replace', 'resize', 'exec', 'sign-and-create', 'set'} & set(args), args)


class CryptographicAttestation(unittest.TestCase):
    REF = 'us-east1-docker.pkg.dev/' + PROJECT + '/repo/app@sha256:' + 'b' * 64

    def test_real_p256_signature_and_declared_key_verify(self):
        self.assertTrue(Verifier(PROJECT, SOURCE, Fake()).attestation(self.REF))

    def test_presence_metadata_is_not_sufficient(self):
        def changed_payload(o):
            o['attestation']['serializedPayload'] = base64.b64encode(b'{}').decode()
            return o
        def changed_signature(o):
            o['attestation']['signatures'][0]['signature'] = base64.b64encode(b'x' * 64).decode()
            return o
        def changed_note(o):
            o['noteName'] = NOTE + '-other'
            return o
        def changed_subject(o):
            o['resourceUri'] = self.REF + '-other'
            return o
        def foreign_key(o):
            return signed_occurrence(self.REF, key=ec.generate_private_key(ec.SECP256R1()))
        def other_signed_subject(o):
            bad = signed_occurrence(self.REF.replace('b' * 64, 'e' * 64))
            bad['resourceUri'] = o['resourceUri']
            return bad
        for change in (changed_payload, changed_signature, changed_note, changed_subject, foreign_key, other_signed_subject):
            with self.subTest(change=change.__name__):
                fake = Fake()
                fake.change_occurrence = change
                self.assertFalse(Verifier(PROJECT, SOURCE, fake).attestation(self.REF))

    def test_changed_authority_kms_key_or_unreviewed_algorithm_is_rejected(self):
        for target in ('attestor', 'extra-key', 'pem', 'kms-key', 'algorithm', 'key-id'):
            with self.subTest(target=target):
                fake = Fake()
                keys = fake.authority['userOwnedGrafeasNote']['publicKeys']
                if target == 'attestor': fake.authority['name'] += '-other'
                if target == 'extra-key': keys.append(deepcopy(keys[0]))
                if target == 'pem': keys[0]['pkixPublicKey']['publicKeyPem'] = 'different'
                if target == 'kms-key': fake.kms['name'] += '0'
                if target == 'algorithm': keys[0]['pkixPublicKey']['signatureAlgorithm'] = 'RSA_SIGN_PKCS1_2048_SHA256'
                if target == 'key-id': keys[0]['id'] += '0'
                self.assertFalse(Verifier(PROJECT, SOURCE, fake).attestation(self.REF))


class SignedSourcePredicate(unittest.TestCase):
    REF = 'us-east1-docker.pkg.dev/' + PROJECT + '/repo/app@sha256:' + 'b' * 64
    MATERIAL = 'moby/buildkit@sha256:99368f3e46177c6405b9740e4461d91cee004128daeecca78d4ceac50ec1da5c'

    def statement(self, *, source=SOURCE, archive='a' * 64, fingerprint='c' * 64,
                  materials=None, worker='secure-infra-worker', digest='b' * 64):
        repo = self.REF.split('@', 1)[0]
        return {'_type': 'https://in-toto.io/Statement/v0.1',
                'predicateType': 'https://cosign.sigstore.dev/attestation/v1',
                'subject': [{'name': repo, 'digest': {'sha256': digest}}],
                'predicate': {'Data': {'schema': 1, 'source_commit': source, 'image': 'app',
                    'worker': worker, 'git_archive_sha256': archive,
                    'input_fingerprint': fingerprint, 'materials': [self.MATERIAL] if materials is None else materials,
                    'platform': 'linux/amd64', 'builder': self.MATERIAL}}}

    def run_with(self, statement):
        calls=[]
        def run(args):
            calls.append(args)
            return 0,json.dumps([{'payload': base64.b64encode(json.dumps(statement).encode()).decode()}])
        verifier=Verifier(PROJECT,SOURCE,run)
        answer=verifier.provenance(self.REF,image='app',archive_sha256='a'*64,
                                  input_fingerprint='c'*64,materials=[self.MATERIAL])
        self.assertEqual(calls[0][1],'verify-attestation')
        self.assertIn('--certificate-github-workflow-sha='+SOURCE,calls[0])
        self.assertIn('--certificate-identity='+IDENTITY,calls[0])
        self.assertIn('--certificate-oidc-issuer='+ISSUER,calls[0])
        return answer

    def test_exact_verified_statement_passes(self):
        self.assertTrue(self.run_with(self.statement()))

    def test_source_material_worker_archive_and_subject_mutations_fail(self):
        for change in ({'source':'e'*40},{'archive':'d'*64},{'fingerprint':'e'*64},
                       {'materials':[]},{'worker':'elsewhere'},{'digest':'e'*64}):
            with self.subTest(change=change):
                self.assertFalse(self.run_with(self.statement(**change)))


if __name__ == '__main__':
    unittest.main()
