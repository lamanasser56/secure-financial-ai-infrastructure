"""Fail-closed orchestration for the twelve current-source disposable probes.

Probe implementations receive a private context and return only named boolean
checks. The runner records no raw request, response, credential, or canary.
"""

import argparse
from datetime import datetime, timezone
import json
import os
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


def case_probes(manifest, run_dir, kubeconfig):
    """Bind each historical case name to its current repository implementation."""
    from live_probe_finance import probe as finance
    from live_probe_identity import probe_k05
    from live_probe_model import probe as model
    from live_probe_network import probe_k01
    from live_probe_ops import probe_o04
    from live_probe_ops_race import probe_o03
    from live_probe_rbac import probe_k02, probe_k03
    from live_probe_session import probe_r01
    from live_probe_worker import probe_d04

    probes = {
        'D02': lambda: model(kubeconfig),
        'D06': lambda: finance('D06', kubeconfig),
        'D04': lambda: probe_d04(kubeconfig),
        'D05': lambda: finance('D05', kubeconfig),
        'D07': lambda: finance('D07', kubeconfig),
        'O03': lambda: probe_o03(kubeconfig, run_dir, manifest),
        'O04': lambda: probe_o04(kubeconfig),
        'K01': lambda: probe_k01(kubeconfig),
        'K02': lambda: probe_k02(kubeconfig),
        'K03': lambda: probe_k03(kubeconfig),
        'K05': lambda: probe_k05(kubeconfig, manifest['disposable_project_id']),
        'R01': lambda: probe_r01(kubeconfig, run_dir, manifest['run_id']),
    }
    if set(probes) != set(CASE_ORDER):
        raise RuntimeError('assessment:case_binding_incomplete')
    return probes


def run_all(manifest, run_dir, *, kubeconfig, probes, ledger_reader,
            janitor_status, cleanup):
    """Run all cases in order and require confirmed cleanup even after failure."""
    if set(probes) != set(CASE_ORDER):
        raise RuntimeError('assessment:case_binding_incomplete')
    if manifest.get('cost_ceiling_usd') != 50:
        raise RuntimeError('assessment:cost_ceiling_changed')
    run_dir = Path(run_dir)
    failure = None
    try:
        for case in CASE_ORDER:
            run_case(manifest, run_dir, case, probes[case], kubeconfig=kubeconfig,
                     ledger_reader=ledger_reader, janitor_status=janitor_status)
    except Exception as exc:
        failure = type(exc).__name__
    finally:
        outcome = cleanup(manifest, run_dir)
        write_receipt(run_dir / 'evidence' / 'operator-cleanup.json', outcome)
    passed = failure is None and outcome.get('result') == 'PASS'
    summary = {'run_id': manifest['run_id'], 'source_commit': manifest['source_commit'],
               'result': 'PASS' if passed else 'INCONCLUSIVE',
               'cases_passed': sum(json.loads((run_dir / 'evidence' /
                   ('case-' + case + '-result.json')).read_text()).get('result') == 'PASS'
                   for case in CASE_ORDER if (run_dir / 'evidence' /
                   ('case-' + case + '-result.json')).is_file()),
               'cleanup_passed': outcome.get('result') == 'PASS',
               'failure_type': failure}
    write_receipt(run_dir / 'evidence' / 'final-summary.json', summary)
    if not passed:
        raise RuntimeError('assessment:live_run_inconclusive')
    return summary


def cleanup_disposable(manifest, run_dir):
    from janitor import cleanup, write_receipt
    from operator_cleanup import destroy
    try:
        return destroy(manifest, run_dir)
    except Exception:
        fallback = cleanup(manifest)
        write_receipt(Path(run_dir) / 'evidence' / 'operator-cleanup-fallback.json', fallback)
        return fallback


def main():
    from janitor import load_manifest
    from live_case_guard import read as read_ledgers
    from operator_janitor import github_api, watch_running

    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if not args.execute or not token:
        raise SystemExit('assessment:explicit_execute_and_github_token_required')
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    kubeconfig = args.run_dir / 'kube' / 'kubeconfig'
    if not kubeconfig.is_file():
        raise SystemExit('assessment:private_kubeconfig_required')
    probes = case_probes(manifest, args.run_dir, kubeconfig)
    result = run_all(manifest, args.run_dir, kubeconfig=kubeconfig, probes=probes,
                     ledger_reader=read_ledgers,
                     janitor_status=lambda run: watch_running(manifest['run_id'], run,
                         api=lambda method, path, payload=None: github_api(token, method, path, payload)),
                     cleanup=cleanup_disposable)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
