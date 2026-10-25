"""Versioned, release-bound attack evidence shared by the owner writer and console reader.

Only declared case IDs, verdicts, times and public hashes cross this boundary. This is an
operator report matching a selected release, not an independent signature or live scan.
"""
import datetime
import json
import re

CONFIGMAP, NAMESPACE, KEY = 'attack-results', 'apps', 'attack-suite.json'
SUITE, VERSION = 'agent-platform-attacks', 2
SHA = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
CASE = re.compile(r'[a-z][a-z0-9_]{2,80}')
TIME = re.compile(r'20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(\+00:00|Z)')

# One case inventory: the executable owner registry must match it exactly. Display
# wording is served with the verdict, never inferred from PASS by the browser.
CASES = {
    'release_preflight': ('control', 'Selected release readiness', 'Image proofs and workload readiness'),
    'financial_setup': ('control', 'Synthetic expense setup', 'Reserved test month'),
    'financial_broker_database_roles': ('attack', 'Read or write beyond broker database rights', 'Database roles and row isolation'),
    'financial_active_capability_boundary': ('attack', 'Use another worker’s active capability', 'User and worker binding'),
    'financial_cross_user_api_and_forged_session': ('attack', 'Forge a session or name another user', 'Authenticated user scope'),
    'financial_show_saras_expenses': ('attack', 'Ask for another user’s expenses', 'Own-row tools'),
    'financial_prompt_injection_in_question': ('attack', 'Hide orders in a question', 'Tool and grounding checks'),
    'financial_filter_bypass_merchant_stays_grounded': ('attack', 'Hide orders in a merchant name', 'Grounding after tool data'),
    'financial_ungrounded_record_claim_feature3': ('attack', 'Claim an unrecorded approval', 'Grounding checks'),
    'financial_question_figure_not_evidence': ('attack', 'Use a question’s number as evidence', 'Grounding checks'),
    'financial_merchant_with_digits_answers': ('control', 'Answer about a merchant containing digits', 'Expected merchant and amount'),
    'gateway_redaction_failure_rejected': ('attack', 'Send a request while redaction is unavailable', 'Mandatory model boundary'),
    'financial_login_lockout_per_username': ('attack', 'Split password guesses across spoofed addresses', 'Current-process login limit'),
    'financial_session_epoch_restart': ('attack', 'Reuse a session after its owner restarts', 'Session epoch'),
    'financial_fixture_cleanup': ('control', 'Remove this run’s synthetic expenses', 'Owned fixture cleanup'),
    'financial_transport_cleanup': ('control', 'Close this run’s connection', 'Owned transport cleanup'),
    'unsigned_image_rejected': ('attack', 'Admit an unattested image', 'Binary Authorization admission'),
    'no_public_exposure': ('attack', 'Expose a service publicly', 'Exposure quotas and inventory'),
    'egress_containment': ('attack', 'Reach a forbidden destination', 'Current network roles'),
    'ops_agent_cannot_change_onboarded_agents': ('attack', 'Let the observer change an agent', 'Read-only observer identity'),
    'ops_stale_approval_refused': ('attack', 'Forge, replay or reuse a stale approval', 'Independent approval executor'),
    'ops_log_injection_adds_no_action_and_no_text': ('attack', 'Plant an instruction in a workload log', 'Logs remain untrusted data'),
    'known_secret_patterns_absent': ('control', 'Scan available logs and environment literals', 'Known credential patterns only'),
}


def timestamp(value):
    if type(value) is not str or not TIME.fullmatch(value):
        raise ValueError('attack_results:time')
    try:
        datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('attack_results:time') from None
    return value


def binding(value):
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {'id', 'source_commit', 'images'}
            or type(value['id']) is not str or not re.fullmatch(r'[0-9a-f]{64}', value['id'])
            or type(value['source_commit']) is not str or not SHA.fullmatch(value['source_commit'])
            or type(value['images']) is not list or not 0 < len(value['images']) <= 32
            or any(type(d) is not str or not DIGEST.fullmatch(d) for d in value['images'])
            or value['images'] != sorted(set(value['images']))):
        raise ValueError('attack_results:release')
    return {'id': value['id'], 'source_commit': value['source_commit'], 'images': list(value['images'])}


def sanitize(data):
    """Current producer contract. Missing, duplicate or unknown required cases cannot look complete."""
    if (type(data) is not dict or type(data.get('schema_version')) is not int or data['schema_version'] != VERSION or data.get('suite') != SUITE
            or type(data.get('run_id')) is not str or not re.fullmatch(r'[0-9a-f]{32}', data['run_id'])
            or type(data.get('results')) is not list or len(data['results']) != len(CASES)):
        raise ValueError('attack_results:shape')
    runner = data.get('runner_commit')
    if runner is not None and (type(runner) is not str or not SHA.fullmatch(runner)):
        raise ValueError('attack_results:runner')
    rows, seen = [], set()
    completed = timestamp(data.get('completed_at'))
    for row in data['results']:
        if (type(row) is not dict or type(row.get('case')) is not str or row['case'] not in CASES
                or row['case'] in seen or row.get('kind') != CASES[row['case']][0]
                or row.get('verdict') not in ('PASS', 'FAIL', 'NOT_EXERCISED')
                or row.get('result') != ('PASS' if row['verdict'] == 'PASS' else 'FAIL')):
            raise ValueError('attack_results:case')
        seen.add(row['case'])
        at = timestamp(row.get('at'))
        if datetime.datetime.fromisoformat(at.replace('Z', '+00:00')) > datetime.datetime.fromisoformat(completed.replace('Z', '+00:00')):
            raise ValueError('attack_results:order')
        rows.append({key: row[key] for key in ('case', 'kind', 'verdict', 'result', 'at')})
    return {'schema_version': VERSION, 'suite': SUITE, 'run_id': data['run_id'],
            'runner_commit': runner, 'release': binding(data.get('release')),
            'completed_at': completed, 'results': rows}


def historical(data):
    """Read a pre-versioned mounted report as unbound history, never as current qualification.

    No bundled result fallback and no free-form owner notes. Unknown old IDs are not
    echoed: only an ordinal and the recorded outcome survive this migration reader.
    """
    if (type(data) is not dict or 'schema_version' in data or data.get('suite') != SUITE
            or type(data.get('results')) is not list or not 0 < len(data['results']) <= 64):
        raise ValueError('attack_results:historical_shape')
    rows, seen = [], set()
    for index, row in enumerate(data['results'], 1):
        if (type(row) is not dict or type(row.get('case')) is not str or not CASE.fullmatch(row['case'])
                or row['case'] in seen or row.get('result') not in ('PASS', 'FAIL')):
            raise ValueError('attack_results:historical_case')
        seen.add(row['case'])
        rows.append({'case': 'archived_case_' + str(index), 'label': CASES.get(row['case'], ('', 'Archived check'))[1],
                     'kind': 'historical', 'result': row['result'], 'verdict': 'RECORDED_' + row['result'],
                     'at': timestamp(row.get('at')), 'purpose': 'Original control semantics unqualified'})
    return {'schema_version': 1, 'suite': SUITE, 'run_id': None, 'runner_commit': None,
            'release': None, 'completed_at': timestamp(data.get('completed_at')), 'results': rows}


def view(data, expected):
    if type(data) is dict and 'schema_version' not in data:
        report, match = historical(data), 'historical'
    else:
        report = sanitize(data)
        match = 'unbound' if report['release'] is None or expected is None else 'current' if report['release'] == expected else 'different_release'
        for row in report['results']:
            _, row['label'], row['purpose'] = CASES[row['case']]
    groups = {}
    for kind in ('attack', 'control', 'historical'):
        rows = [r for r in report['results'] if r['kind'] == kind]
        groups[kind] = {'total': len(rows), 'passed': sum(r['verdict'] == 'PASS' for r in rows),
                        'failed': sum(r['verdict'] == 'FAIL' for r in rows),
                        'not_exercised': sum(r['verdict'] == 'NOT_EXERCISED' for r in rows)}
    return dict(report, available=True, binding=match, source='mounted', file='ConfigMap apps/attack-results',
                complete=match != 'historical' and report['runner_commit'] is not None and all(r['verdict'] != 'NOT_EXERCISED' for r in report['results']),
                summary=groups)


def configmap(data):
    return {'apiVersion': 'v1', 'kind': 'ConfigMap',
            'metadata': {'name': CONFIGMAP, 'namespace': NAMESPACE, 'labels': {'app.kubernetes.io/part-of': 'agent-platform'}},
            'data': {KEY: json.dumps(sanitize(data), sort_keys=True)}}
