"""Read pinned retained security evidence; never fabricate a current qualification."""
from datetime import date
import hashlib
import importlib.util
import json
from pathlib import Path

from runtime.agents.operations import OperationsBlocked

ROOT = Path(__file__).resolve().parents[2]


def read_subject(config):
    """Operator binds exact retained bytes, signer and subject outside the browser.

    Signature result is a historical, trusted native-verifier receipt. This reader
    does not perform a new cryptographic Cosign verification or provider call.
    """
    if set(config) != {'subject', 'source', 'signer', 'issuer', 'files'}:
        raise OperationsBlocked('INVALID_REQUEST')
    files = {}
    for name in ('scan', 'signature', 'kev', 'exceptions', 'verification', 'release'):
        record = config['files'][name]
        path = Path(record['path'])
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise OperationsBlocked('UNSAFE_FILE')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record['integrity']:
            raise OperationsBlocked('EVIDENCE_CHANGED')
        files[name] = json.loads(data)
    native, release = files['verification'], files['release']
    if (native['result'] != 'PASS' or release['result'] != 'PASS'
            or native['registry_digest_reference'] != config['subject']
            or release['registry_digest_reference'] != config['subject']
            or native['source_commit'] != config['source'] or release['source_commit'] != config['source']
            or native['native_cosign_verification'] != 'PASS exact issuer/workflow/source/dispatch/digest'
            or native['reviewed_release_subject_receipt_sha256'] != config['files']['release']['integrity']
            or release['evidence_sha256']['trivy.json'] != config['files']['scan']['integrity']
            or release['evidence_sha256']['cosign-verification.json'] != config['files']['signature']['integrity']):
        raise OperationsBlocked('EVIDENCE_CHANGED')
    signature = files['signature']
    digest = config['subject'].split('@')[-1]
    if not isinstance(signature, list) or not signature:
        raise OperationsBlocked('EVIDENCE_CHANGED')
    for item in signature:
        critical, optional = item['critical'], item['optional']
        if (critical['image']['docker-manifest-digest'] != digest
                or critical['identity']['docker-reference'] != config['subject'].split('@')[0]
                or optional['Issuer'] != config['issuer'] or optional['Subject'] != config['signer']
                or optional['githubWorkflowSha'] != config['source']
                or optional['githubWorkflowTrigger'] != 'workflow_dispatch'):
            raise OperationsBlocked('EVIDENCE_CHANGED')
    spec = importlib.util.spec_from_file_location('vulnerability_policy',
        ROOT / 'scripts/evaluate-container-vulnerability-policy.py')
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    allowed, _ = evaluator.evaluate(files['scan'], config['subject'], files['kev'], files['exceptions'], date.today())
    return {'subject': config['subject'], 'source': config['source'],
        'vulnerability_policy': 'allow' if allowed else 'deny',
        'signature_evidence': 'historical_native_verified_receipt',
        'fresh_signature_verification': False, 'scope': 'retained_exact_image_bytes',
        'historical_verified_at': native['verified_at'],
        'current_application_qualified': False,
        'evidence_integrities': {k: v['integrity'] for k, v in config['files'].items()},
        'limitations': ['NOT_A_NEW_SCAN_OR_SIGNATURE', 'NOT_REDACTION_QUALIFICATION',
                         'NOT_PROVIDER_AUTHORITY']}
