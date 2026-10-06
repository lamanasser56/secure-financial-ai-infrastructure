#!/usr/bin/env python3
"""Owner-only exact-subject keyless signing; requires separate execution approval.

Uses the existing owner's interactive Dex/Google identity. Ambient VM/cloud
identities are disabled. The identity is public in Sigstore transparency records;
it is retained privately in the review binding, never printed by this program.
No signing key, IAM, WIF or registry policy change is implemented here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.agents.operations import private_directory
from runtime.agents.service_restoration import private_file


def run(args):
    if os.environ.get('PORTFOLIO_NATIVE_OWNER_SIGNING_ACK')!='I_ACKNOWLEDGE_EXACT_OWNER_SUBJECT_AND_PUBLIC_SIGSTORE_IDENTITY':raise ValueError
    if args.subject and not re.fullmatch(r'us-east1-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/sdp-evaluation-images/agent-demo-(gateway|database)@sha256:[a-f0-9]{64}',args.subject):raise ValueError
    if not re.fullmatch('[a-f0-9]{40}',args.source):raise ValueError
    raw=private_file(args.signer)
    if hashlib.sha256(raw).hexdigest()!=args.signer_integrity:raise ValueError
    signer=json.loads(raw)
    if args.subject and args.subject.split('/')[1]!=signer['project_id']:raise ValueError
    if args.manifest and (not args.manifest_integrity or hashlib.sha256(private_file(args.manifest)).hexdigest()!=args.manifest_integrity):raise ValueError
    if (signer['certificate_oidc_issuer']!='https://oauth2.sigstore.dev/auth'
            or signer['public_transparency_log_identity'] is not True or signer['no_google_vm_identity'] is not True):raise ValueError
    if hashlib.sha256(args.cosign.read_bytes()).hexdigest()!='d437b8f0d30f5dec169337607fcfa0238de1348503e175f1bb5b94330b1ee409':raise ValueError
    directory=private_directory(args.evidence)
    prefix=args.subject.split('/')[-1].split('@')[0] if args.subject else 'program-subjects'
    with (directory/(prefix+'-signing-started.json')).open('x') as stream:
        stream.write(json.dumps({'subject':args.subject,'source':args.source,'automatic_replay':False})+'\n');stream.flush();os.fsync(stream.fileno())
    # Interactive auth instructions remain in a private operator log.
    with (directory/(prefix+'-private-signing.log')).open('xb') as log:
        if args.manifest:
            subprocess.run([str(args.cosign),'sign-blob','--yes','--oidc-disable-ambient-providers',
                '--oidc-issuer',signer['certificate_oidc_issuer'],'--bundle',str(directory/'program-subjects.sigstore.json'),str(args.manifest)],stdout=log,stderr=log,timeout=180,check=True)
            subprocess.run([str(args.cosign),'verify-blob','--certificate-identity',signer['certificate_identity'],
                '--certificate-oidc-issuer',signer['certificate_oidc_issuer'],'--bundle',str(directory/'program-subjects.sigstore.json'),str(args.manifest)],stdout=log,stderr=log,timeout=60,check=True)
            print(json.dumps({'program_manifest_verified':True,'image_signature_claimed':False}))
            return
        subprocess.run([str(args.cosign),'sign','--yes','--oidc-disable-ambient-providers',
            '--oidc-issuer',signer['certificate_oidc_issuer'],'--annotations','source='+args.source,args.subject],
            stdout=log,stderr=log,timeout=180,check=True)
        with (directory/(prefix+'-cosign-verification.json')).open('xb') as result:
            subprocess.run([str(args.cosign),'verify','--certificate-identity',signer['certificate_identity'],
                '--certificate-oidc-issuer',signer['certificate_oidc_issuer'],'--annotations','source='+args.source,args.subject],
                stdout=result,stderr=log,timeout=60,check=True)
    print(json.dumps({'subject':args.subject,'source':args.source,'issuer_owner_source_digest_verified':True,'image_signature_covers_supplied_programs':False}))


if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True);g.add_argument('--subject');g.add_argument('--manifest',type=Path)
    p.add_argument('--manifest-integrity')
    for name in ['source','signer-integrity']:p.add_argument('--'+name,required=True)
    for name in ['signer','cosign','evidence']:p.add_argument('--'+name,type=Path,required=True)
    try:run(p.parse_args())
    except Exception:raise SystemExit('native_owner_signing:FAILED; no automatic repeat') from None
