"""Read-only verification of exact release subjects. No tag/occurrence-presence shortcut.

Cosign verifies Fulcio identity, issuer, transparency proof and workflow revision. Binary Authorization's
signed payload is checked locally against the independently fetched, declared KMS public key.
See https://docs.sigstore.dev/cosign/verifying/verify/ and
https://cloud.google.com/binary-authorization/docs/making-attestations .
"""
import base64
import json
from pathlib import Path
import re
import tempfile

IDENTITY = 'https://github.com/lamanasser56/secure-financial-ai-infrastructure/.github/workflows/agent-platform-images.yml@refs/heads/main'
ISSUER = 'https://token.actions.githubusercontent.com'
ATTESTOR = 'agent-platform-ci'
ALGORITHMS = {'EC_SIGN_P256_SHA256', 'ECDSA_P256_SHA256'}


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


class Verifier:
    def __init__(self, project, source, run, *, cosign='cosign'):
        self.project, self.source, self.run, self.cosign = project, source, run, cosign
        self.key_id = 'projects/' + project + '/locations/us-east1/keyRings/agent-platform/cryptoKeys/binauthz-attestor/cryptoKeyVersions/1'
        self.note = 'projects/' + project + '/notes/agent-platform-attestor'

    def cloud(self, *args):
        rc, raw = self.run(['gcloud', *args, '--project', self.project, '--format=json'])
        if rc:
            raise ValueError('verification source unavailable')
        return decode(raw)

    def signature(self, ref):
        if not isinstance(self.source, str) or not re.fullmatch('[0-9a-f]{40}', self.source):
            return False
        rc, raw = self.run([self.cosign, 'verify', ref, '--output=json',
            '--certificate-identity=' + IDENTITY, '--certificate-oidc-issuer=' + ISSUER,
            '--certificate-github-workflow-sha=' + self.source])
        try:
            values = decode(raw)
            repo, digest = ref.rsplit('@', 1)
            return rc == 0 and isinstance(values, list) and any(
                v['critical']['type'] == 'cosign container image signature'
                and v['critical']['image']['docker-manifest-digest'] == digest
                and v['critical']['identity']['docker-reference'] == repo for v in values)
        except (ValueError, KeyError, TypeError):
            return False

    def attestation(self, ref):
        try:
            authority = self.cloud('container', 'binauthz', 'attestors', 'describe', ATTESTOR)
            keys = authority['userOwnedGrafeasNote']
            if (authority['name'] != 'projects/' + self.project + '/attestors/' + ATTESTOR
                    or keys['noteReference'] != self.note or len(keys['publicKeys']) != 1):
                return False
            key = keys['publicKeys'][0]
            if key['id'] != self.key_id or key['pkixPublicKey']['signatureAlgorithm'] not in ALGORITHMS:
                return False
            kms = self.cloud('kms', 'keys', 'versions', 'get-public-key', '1', '--location', 'us-east1',
                             '--keyring', 'agent-platform', '--key', 'binauthz-attestor')
            pem = kms['pem']
            if (kms['name'] != self.key_id or kms['algorithm'] != 'EC_SIGN_P256_SHA256'
                    or pem.strip() != key['pkixPublicKey']['publicKeyPem'].strip()):
                return False
            occurrences = self.cloud('container', 'binauthz', 'attestations', 'list',
                                      '--attestor', ATTESTOR, '--artifact-url', ref)
            return isinstance(occurrences, list) and any(self._occurrence(o, ref, pem) for o in occurrences)
        except (ValueError, KeyError, TypeError, AttributeError):
            return False

    def _occurrence(self, occurrence, ref, pem):
        try:
            if (occurrence['noteName'] != self.note or occurrence.get('kind') != 'ATTESTATION'
                    or occurrence['resourceUri'] not in (ref, 'https://' + ref)):
                return False
            attestation = occurrence['attestation']
            payload = base64.b64decode(attestation['serializedPayload'], validate=True)
            if len(payload) > 65536:
                return False
            value = decode(payload)
            repo, digest = ref.rsplit('@', 1)
            if value['critical'] != {'identity': {'docker-reference': repo},
                                     'image': {'docker-manifest-digest': digest},
                                     'type': 'Google cloud binauthz container signature'}:
                return False
            for signed in attestation['signatures']:
                if signed['publicKeyId'] != self.key_id:
                    continue
                signature = base64.b64decode(signed['signature'], validate=True)
                if not signature or len(signature) > 1024:
                    continue
                with tempfile.TemporaryDirectory(prefix='release-verification-') as directory:
                    paths = [Path(directory) / name for name in ('key.pem', 'payload', 'signature')]
                    for path, content in zip(paths, (pem.encode(), payload, signature)):
                        path.write_bytes(content)
                        path.chmod(0o600)
                    rc, _ = self.run(['openssl', 'dgst', '-sha256', '-verify', str(paths[0]),
                                      '-signature', str(paths[2]), str(paths[1])])
                    if rc == 0:
                        return True
        except (ValueError, KeyError, TypeError, OSError):
            return False
        return False
