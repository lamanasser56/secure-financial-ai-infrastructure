"""KMS attestation verification against the output shapes gcloud 582 returns for Binary Authorization and Cloud KMS.

The fixtures copy the observed field layout (sanitised: placeholder project and service-agent number, a test P-256
key instead of the real attestor key). Attestor and occurrence name the key version by its full KMS resource name,
`get-public-key` prints one PEM block, and occurrence bytes fields are padded base64url.
"""
import base64
from copy import deepcopy
import json
import subprocess
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from agent_platform.release_verify import KMS_RESOURCE, Verifier, decode_bytes

PROJECT, SOURCE = 'example-project', 'd' * 40
KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())
KEY_ID = 'projects/' + PROJECT + '/locations/us-east1/keyRings/agent-platform/cryptoKeys/binauthz-attestor/cryptoKeyVersions/1'
NOTE = 'projects/' + PROJECT + '/notes/agent-platform-attestor'
REF = 'us-east1-docker.pkg.dev/' + PROJECT + '/sdp-evaluation-images/agent-financial@sha256:' + 'b' * 64


def pem(key):
    return key.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def b64url(raw):
    return base64.urlsafe_b64encode(raw).decode()


def payload(ref):
    # Binary Authorization's serialized payload, indented as gcloud sign-and-create writes it.
    repo, digest = ref.rsplit('@', 1)
    return (json.dumps({'critical': {'identity': {'docker-reference': repo},
                                     'image': {'docker-manifest-digest': digest},
                                     'type': 'Google cloud binauthz container signature'}}, indent=2) + '\n').encode()


def url_safe_signature(key, raw):
    # ECDSA is randomised; keep signing until the encoding exercises the base64url-only characters.
    while True:
        signature = key.sign(raw, ec.ECDSA(hashes.SHA256()))
        encoded = b64url(signature)
        if '-' in encoded or '_' in encoded:
            return signature, encoded


def attestor():
    return {'etag': '"AAAAAAAAAAAA"', 'name': 'projects/' + PROJECT + '/attestors/agent-platform-ci',
            'updateTime': '2026-10-10T17:01:48.184784Z',
            'userOwnedGrafeasNote': {
                'delegationServiceAccountEmail': 'service-000000000000@gcp-sa-binaryauthorization.iam.gserviceaccount.com',
                'noteReference': NOTE,
                'publicKeys': [{'id': KMS_RESOURCE + KEY_ID,
                                'pkixPublicKey': {'publicKeyPem': pem(KEY),
                                                  'signatureAlgorithm': 'ECDSA_P256_SHA256'}}]}}


def kms_version():
    return {'algorithm': 'EC_SIGN_P256_SHA256', 'createTime': '2026-10-10T17:01:33.565240793Z',
            'generateTime': '2026-10-10T17:01:33.630790394Z', 'name': KEY_ID,
            'protectionLevel': 'SOFTWARE', 'state': 'ENABLED'}


def occurrence(ref, *, key=KEY, signed_ref=None):
    raw = payload(signed_ref or ref)
    _, signature = url_safe_signature(key, raw)
    return {'attestation': {'serializedPayload': b64url(raw),
                            'signatures': [{'publicKeyId': KMS_RESOURCE + KEY_ID, 'signature': signature}]},
            'createTime': '2026-10-26T17:27:09.739848Z', 'kind': 'ATTESTATION',
            'name': 'projects/' + PROJECT + '/occurrences/00000000-0000-0000-0000-000000000000',
            'noteName': NOTE, 'resourceUri': ref, 'updateTime': '2026-10-26T17:27:09.739848Z'}


class Gcloud:
    """Answers the four read-only gcloud calls the way gcloud 582 does; openssl runs for real."""

    def __init__(self):
        self.attestor, self.kms, self.public_key = attestor(), kms_version(), pem(KEY)
        self.occurrences = [occurrence(REF)]
        self.calls = []

    def __call__(self, args):
        args = list(map(str, args))
        self.calls.append(args)
        if args[0] == 'openssl':
            result = subprocess.run(args, capture_output=True, text=True)
            return result.returncode, result.stdout
        text = ' '.join(args)
        if 'attestors describe' in text:
            return 0, json.dumps(self.attestor, indent=2)
        if 'versions describe' in text:
            return 0, json.dumps(self.kms, indent=2)
        if 'get-public-key' in text:
            # With --format=json gcloud still prints the PEM, then an empty resource list.
            return 0, self.public_key + ('[]\n' if '--format=json' in args else '')
        if 'attestations list' in text:
            return 0, json.dumps(self.occurrences, indent=2)
        return 1, ''


def verify(fake, ref=REF):
    return Verifier(PROJECT, SOURCE, fake).attestation(ref)


class ObservedShapes(unittest.TestCase):
    def test_observed_gcloud_output_verifies(self):
        fake = Gcloud()
        self.assertTrue(verify(fake))
        public_key_call = next(call for call in fake.calls if 'get-public-key' in call)
        self.assertNotIn('--format=json', public_key_call)

    def test_der_signature_of_every_length_and_padding_decodes(self):
        raw = payload(REF)
        for length in (70, 71, 72):
            with self.subTest(length=length):
                while True:
                    signature = KEY.sign(raw, ec.ECDSA(hashes.SHA256()))
                    if len(signature) == length:
                        break
                fake = Gcloud()
                fake.occurrences[0]['attestation']['signatures'][0]['signature'] = b64url(signature)
                self.assertTrue(verify(fake))

    def test_decode_bytes_accepts_only_padded_base64url(self):
        self.assertEqual(decode_bytes('-_8='), b'\xfb\xff')
        self.assertEqual(decode_bytes('-_-_'), b'\xfb\xff\xbf')
        for value in ('+/8=', '-_8', '-_8==', '-_8=\n', ' -_8=', '', None, 7):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    decode_bytes(value)


class Rejections(unittest.TestCase):
    def assertRejected(self, change):
        fake = Gcloud()
        change(fake)
        self.assertFalse(verify(fake))

    def test_wrong_key_id(self):
        def attestor_relative(f): f.attestor['userOwnedGrafeasNote']['publicKeys'][0]['id'] = KEY_ID
        def attestor_other_version(f): f.attestor['userOwnedGrafeasNote']['publicKeys'][0]['id'] = KMS_RESOURCE + KEY_ID[:-1] + '2'
        def attestor_other_service(f): f.attestor['userOwnedGrafeasNote']['publicKeys'][0]['id'] = '//cloudkms.googleapis.com/v2/' + KEY_ID
        def occurrence_relative(f): f.occurrences[0]['attestation']['signatures'][0]['publicKeyId'] = KEY_ID
        def occurrence_other_version(f):
            f.occurrences[0]['attestation']['signatures'][0]['publicKeyId'] = KMS_RESOURCE + KEY_ID[:-1] + '2'
        def kms_name_prefixed(f): f.kms['name'] = KMS_RESOURCE + KEY_ID
        def kms_other_version(f): f.kms['name'] = KEY_ID[:-1] + '2'
        for change in (attestor_relative, attestor_other_version, attestor_other_service, occurrence_relative,
                       occurrence_other_version, kms_name_prefixed, kms_other_version):
            with self.subTest(change=change.__name__):
                self.assertRejected(change)

    def test_wrong_key(self):
        def foreign_signer(f): f.occurrences = [occurrence(REF, key=OTHER_KEY)]
        def attestor_pem_differs(f):
            f.attestor['userOwnedGrafeasNote']['publicKeys'][0]['pkixPublicKey']['publicKeyPem'] = pem(OTHER_KEY)
        def kms_pem_differs(f): f.public_key = pem(OTHER_KEY)
        def both_swapped_but_signed_by_declared(f):
            f.public_key = pem(OTHER_KEY)
            f.attestor['userOwnedGrafeasNote']['publicKeys'][0]['pkixPublicKey']['publicKeyPem'] = pem(OTHER_KEY)
        def kms_disabled(f): f.kms['state'] = 'DISABLED'
        def kms_other_algorithm(f): f.kms['algorithm'] = 'EC_SIGN_P384_SHA384'
        def attestor_other_algorithm(f):
            f.attestor['userOwnedGrafeasNote']['publicKeys'][0]['pkixPublicKey']['signatureAlgorithm'] = 'RSA_SIGN_PKCS1_2048_SHA256'
        def extra_attestor_key(f):
            keys = f.attestor['userOwnedGrafeasNote']['publicKeys']
            keys.append(deepcopy(keys[0]))
        for change in (foreign_signer, attestor_pem_differs, kms_pem_differs, both_swapped_but_signed_by_declared,
                       kms_disabled, kms_other_algorithm, attestor_other_algorithm, extra_attestor_key):
            with self.subTest(change=change.__name__):
                self.assertRejected(change)

    def test_public_key_output_must_be_exactly_one_pem_block(self):
        def json_trailer(f): f.public_key = pem(KEY) + '[]\n'
        def json_object(f): f.public_key = json.dumps({'pem': pem(KEY)})
        def two_blocks(f): f.public_key = pem(KEY) + pem(KEY)
        def missing_newline(f): f.public_key = pem(KEY).rstrip('\n')
        for change in (json_trailer, json_object, two_blocks, missing_newline):
            with self.subTest(change=change.__name__):
                self.assertRejected(change)

    def test_tampered_payload(self):
        def byte_changed(f):
            raw = bytearray(payload(REF))
            raw[raw.index(b'b' * 8)] = ord('c')
            f.occurrences[0]['attestation']['serializedPayload'] = b64url(bytes(raw))
        def extra_field(f):
            raw = payload(REF).replace(b'"critical"', b'"optional": {}, "critical"', 1)
            f.occurrences[0]['attestation']['serializedPayload'] = b64url(raw)
        def empty_object(f): f.occurrences[0]['attestation']['serializedPayload'] = b64url(b'{}')
        def standard_alphabet(f):
            value = f.occurrences[0]['attestation']['serializedPayload']
            f.occurrences[0]['attestation']['serializedPayload'] = value.replace('A', '+', 1)
        for change in (byte_changed, extra_field, empty_object, standard_alphabet):
            with self.subTest(change=change.__name__):
                self.assertRejected(change)

    def test_tampered_signature(self):
        def flipped_byte(f):
            signed = f.occurrences[0]['attestation']['signatures'][0]
            raw = bytearray(decode_bytes(signed['signature']))
            raw[-1] ^= 1
            signed['signature'] = b64url(bytes(raw))
        def standard_base64(f):
            signed = f.occurrences[0]['attestation']['signatures'][0]
            signed['signature'] = base64.b64encode(decode_bytes(signed['signature'])).decode()
        def padding_stripped(f):
            raw = payload(REF)
            while True:
                signature = KEY.sign(raw, ec.ECDSA(hashes.SHA256()))
                if len(signature) % 3:
                    break
            f.occurrences[0]['attestation']['signatures'][0]['signature'] = b64url(signature).rstrip('=')
        def empty(f): f.occurrences[0]['attestation']['signatures'][0]['signature'] = ''
        def oversized(f): f.occurrences[0]['attestation']['signatures'][0]['signature'] = b64url(b'x' * 1025)
        for change in (flipped_byte, standard_base64, padding_stripped, empty, oversized):
            with self.subTest(change=change.__name__):
                self.assertRejected(change)

    def test_wrong_digest(self):
        other = REF.replace('b' * 64, 'e' * 64)
        def signed_for_other_digest(f): f.occurrences = [occurrence(REF, signed_ref=other)]
        def occurrence_for_other_digest(f): f.occurrences = [occurrence(other)]
        def other_repository(f):
            f.occurrences = [occurrence(REF, signed_ref=REF.replace('agent-financial@', 'agent-platform-app@'))]
        def no_occurrence(f): f.occurrences = []
        for change in (signed_for_other_digest, occurrence_for_other_digest, other_repository, no_occurrence):
            with self.subTest(change=change.__name__):
                self.assertRejected(change)
        fake = Gcloud()
        self.assertFalse(verify(fake, other))


if __name__ == '__main__':
    unittest.main()
