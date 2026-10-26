#!/usr/bin/env python3
"""Reuse an image already pushed under the immutable tag sha-<S>, only after verifying it as a fresh build.

The registry refuses to move sha-<S>, and a rebuild is not byte-identical, so a second run for the same S (a forced
dispatch after the automatic run, or the reverse) must not rebuild. `lookup` reads the tag through the registry API
(404 = absent; anything else unexpected fails closed). `verify` requires the keyless signature from this workflow at S
and the signed source/material predicate recomputed for S, using the release verifier. Nothing is pushed, signed,
retagged or overwritten here.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

ACCEPT = ', '.join(('application/vnd.oci.image.index.v1+json', 'application/vnd.oci.image.manifest.v1+json',
                    'application/vnd.docker.distribution.manifest.list.v2+json',
                    'application/vnd.docker.distribution.manifest.v2+json'))
NAME = re.compile(r'[a-z][a-z0-9-]{0,62}')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')


def lookup(registry, project, repository, image, source, token, *, open_url=urllib.request.urlopen):
    """Digest of `image:sha-<source>`, or None when the registry reports the tag (or image) unknown."""
    if not (re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', project) and NAME.fullmatch(image)
            and NAME.fullmatch(repository) and re.fullmatch(r'[0-9a-f]{40}', source) and token):
        raise ValueError('invalid lookup input')
    url = 'https://%s/v2/%s/%s/%s/manifests/sha-%s' % (registry, project, repository, image, source)
    auth = base64.b64encode(('oauth2accesstoken:' + token).encode()).decode()
    request = urllib.request.Request(url, method='HEAD', headers={'Accept': ACCEPT, 'Authorization': 'Basic ' + auth})
    try:
        with open_url(request, timeout=60) as response:
            status, digest = response.status, response.headers.get('Docker-Content-Digest', '')
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError('registry lookup failed: HTTP %d' % error.code) from None
    if status != 200 or not DIGEST.fullmatch(digest):
        raise RuntimeError('registry lookup returned no exact digest')
    return digest


def verify(ref, predicate, verifier):
    """Raise unless `ref` carries this workflow's keyless signature at S and the signed predicate for S."""
    if not verifier.signature(ref):
        raise RuntimeError('existing subject lacks the keyless signature of this workflow at S')
    if not verifier.provenance(ref, image=predicate['image'], archive_sha256=predicate['git_archive_sha256'],
                               input_fingerprint=predicate['input_fingerprint'],
                               materials=predicate['materials']):
        raise RuntimeError('existing subject lacks the signed source/material predicate for S: '
                           + str(verifier.provenance_issue))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    find = commands.add_parser('lookup')
    for name in ('--registry', '--project', '--repository', '--image', '--source'):
        find.add_argument(name, required=True)
    check = commands.add_parser('verify')
    check.add_argument('--ref', required=True)
    check.add_argument('--project', required=True)
    check.add_argument('--source', required=True)
    check.add_argument('--predicate', type=Path, required=True)
    check.add_argument('--cosign', default='cosign')
    args = parser.parse_args()
    if args.command == 'lookup':
        # The short-lived token arrives in the environment, never on the command line.
        digest = lookup(args.registry, args.project, args.repository, args.image, args.source,
                        os.environ.get('ACCESS_TOKEN', ''))
        print(digest or '')
        return
    from agent_platform.release_verify import Verifier

    def runner(command):
        result = subprocess.run(command, capture_output=True, text=True)
        return result.returncode, result.stdout
    verify(args.ref, json.loads(args.predicate.read_text()), Verifier(args.project, args.source, runner,
                                                                       cosign=args.cosign))
    print('existing sha-<S> subject: keyless signature at S and source/material predicate verified')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError) as error:
        sys.exit(str(error))
