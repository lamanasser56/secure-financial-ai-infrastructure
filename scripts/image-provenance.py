#!/usr/bin/env python3
"""Produce a source/material predicate from the validated current input plan and worker receipt."""
import argparse
import json
from pathlib import Path
import re
import subprocess

BUILDKIT = 'moby/buildkit@sha256:99368f3e46177c6405b9740e4461d91cee004128daeecca78d4ceac50ec1da5c'


def predicate(plan, receipt, image, source):
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('invalid source')
    if plan.get('source_commit') != source or receipt.get('source_commit') != source:
        raise ValueError('source mismatch')
    match = [entry for entry in plan.get('images', []) if entry.get('image') == image]
    if len(match) != 1 or receipt.get('image') != image or receipt.get('worker') != 'secure-infra-worker':
        raise ValueError('image/worker mismatch')
    entry = match[0]
    if not re.fullmatch(r'[0-9a-f]{64}', receipt.get('git_archive_sha256', '')):
        raise ValueError('invalid git archive digest')
    if not re.fullmatch(r'[0-9a-f]{64}', entry.get('fingerprint', '')):
        raise ValueError('invalid input fingerprint')
    materials = entry.get('materials')
    if not isinstance(materials, list) or materials != sorted(set(materials)):
        raise ValueError('noncanonical materials')
    if BUILDKIT not in materials:
        materials = sorted(set(materials + [BUILDKIT]))
    return {'schema': 1, 'source_commit': source, 'image': image, 'worker': 'secure-infra-worker',
            'git_archive_sha256': receipt['git_archive_sha256'],
            'input_fingerprint': entry['fingerprint'], 'materials': materials,
            'platform': 'linux/amd64', 'builder': BUILDKIT}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--worker-receipt', type=Path)
    parser.add_argument('--image')
    parser.add_argument('--source')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--verify-ref')
    parser.add_argument('--project')
    parser.add_argument('--predicate', type=Path)
    parser.add_argument('--cosign', default='cosign')
    args = parser.parse_args()
    if args.verify_ref:
        if not all((args.project, args.source, args.predicate)):
            raise SystemExit('missing verification input')
        from agent_platform.release_verify import Verifier
        signed = json.loads(args.predicate.read_text())
        def runner(command):
            result = subprocess.run(command, capture_output=True, text=True)
            return result.returncode, result.stdout
        verifier = Verifier(args.project, args.source, runner, cosign=args.cosign)
        if not verifier.provenance(args.verify_ref, image=signed['image'],
                                   archive_sha256=signed['git_archive_sha256'],
                                   input_fingerprint=signed['input_fingerprint'],
                                   materials=signed['materials']):
            raise SystemExit('cryptographic source/material provenance verification failed')
        print('exact-subject source/material attestation verified')
        return
    if not all((args.plan, args.worker_receipt, args.image, args.source, args.out)):
        raise SystemExit('missing build predicate input')
    value = predicate(json.loads(args.plan.read_text()), json.loads(args.worker_receipt.read_text()),
                      args.image, args.source)
    args.out.write_text(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
    print('source/material predicate prepared for cryptographic signing')


if __name__ == '__main__':
    main()
