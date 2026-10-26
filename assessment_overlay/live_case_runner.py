"""Fail-closed orchestration for the twelve current-source disposable probes.

Probe implementations receive a private context and return only named boolean
checks. The runner records no raw request, response, credential, or canary.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

from janitor import write_receipt
from live_case_guard import CASE_LIMITS, PLANNED_LIMITS, SETUP_LIMITS, case_delta


CASE_ORDER = ('D02', 'D06', 'D04', 'D05', 'D07', 'O03', 'O04',
              'K01', 'K02', 'K03', 'K05', 'R01')


def readiness(manifest, run_dir, case, *, now, janitor_status):
    """Refuse cases out of order or after the independent cleanup watch stops."""
    if case not in CASE_ORDER:
        raise ValueError('assessment:unknown_case')
    if now >= datetime.fromisoformat(manifest['deadline_at']):
        raise RuntimeError('assessment:deadline_passed')
    evidence = Path(run_dir) / 'evidence'
    applied = json.loads((evidence / 'bundle-applied.json').read_text())
    armed = json.loads((evidence / 'janitor-armed.json').read_text())
    if (applied.get('run_id') != manifest['run_id']
            or applied.get('source_commit') != manifest['source_commit']
            or applied.get('bundle_sha256') != manifest['bundle_sha256']
            or set(applied.get('verified_runtime_images', [])) != set(manifest['image_digests'])
            or armed.get('run_id') != manifest['run_id']
            or armed.get('watch_step_in_progress') is not True
            or janitor_status(armed['workflow_run_id']) is not True):
        raise RuntimeError('assessment:release_or_janitor_not_ready')
    index = CASE_ORDER.index(case)
    for prior in CASE_ORDER[:index]:
        receipt = json.loads((evidence / ('case-' + prior + '-result.json')).read_text())
        if receipt.get('run_id') != manifest['run_id'] or receipt.get('result') != 'PASS':
            raise RuntimeError('assessment:prior_case_not_passed')
    if any((evidence / ('case-' + later + '-result.json')).exists() for later in CASE_ORDER[index:]):
        raise RuntimeError('assessment:case_or_later_already_started')


def run_case(manifest, run_dir, case, probe, *, kubeconfig, ledger_reader,
             janitor_status, now=None):
    """Run one bounded case; every failure blocks the next case.

    The probe is injected so offline tests exercise the exact guard without a
    cluster. Production case implementations are bound explicitly by the CLI.
    """
    now = now or datetime.now(timezone.utc)
    readiness(manifest, run_dir, case, now=now, janitor_status=janitor_status)
    run_dir = Path(run_dir)
    evidence = run_dir / 'evidence'
    before = ledger_reader(kubeconfig, manifest['run_id'])
    if before['inflight'] or before['completed_redactions'] >= 12 or before['sdk_attempts'] >= 40:
        raise RuntimeError('assessment:manual_stop_or_inflight')
    write_receipt(evidence / ('case-' + case + '-before-ledgers.json'), before)
    checks = None
    error = None
    try:
        checks = probe()
        if (not isinstance(checks, dict) or not checks
                or any(not isinstance(name, str) or not name.isidentifier() or type(value) is not bool
                       for name, value in checks.items())):
            raise ValueError('assessment:probe_must_return_named_booleans')
    except Exception as exc:
        error = type(exc).__name__
    after = ledger_reader(kubeconfig, manifest['run_id'])
    write_receipt(evidence / ('case-' + case + '-after-ledgers.json'), after)
    delta = case_delta(case, before, after)
    index = CASE_ORDER.index(case)
    cumulative = tuple(SETUP_LIMITS[i] + sum(CASE_LIMITS[name][i]
                       for name in CASE_ORDER[:index + 1]) for i in (0, 1))
    if (after['inflight'] or after['completed_redactions'] > cumulative[0]
            or after['sdk_attempts'] > cumulative[1]
            or after['completed_redactions'] >= 12 or after['sdk_attempts'] >= 40
            or cumulative[0] > PLANNED_LIMITS[0] or cumulative[1] > PLANNED_LIMITS[1]):
        raise RuntimeError('assessment:cumulative_or_manual_limit_exceeded')
    receipt = {'run_id': manifest['run_id'], 'case': case,
               'result': 'PASS' if error is None and all(checks.values()) else
                         'INCONCLUSIVE' if error else 'FAIL',
               'checks': checks if error is None else {},
               'error_type': error,
               'redactions': delta[0], 'sdk_attempts': delta[1],
               'synthetic_only': True, 'external_llm_calls_allowed': 0}
    write_receipt(evidence / ('case-' + case + '-result.json'), receipt)
    if receipt['result'] != 'PASS':
        raise RuntimeError('assessment:case_' + receipt['result'].lower())
    return receipt
