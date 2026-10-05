"""Separate fixed synthetic reasoning gate. Never an operational approval path."""
import hashlib
import json
import os
from pathlib import Path
import time

from runtime.agents.credentials import ScopedCredential
from runtime.agents.protocol_preparation import completion_content
from runtime.phase3.adapters import _post_json

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'evaluation/operations/synthetic-reasoning.json'
ACK = 'I_ACKNOWLEDGE_THREE_FIXED_SYNTHETIC_OPERATIONS_REQUESTS'


def cases():
    value = json.loads(CATALOG.read_text())
    assert value['scope'] == 'fixed_synthetic_operations_reasoning'
    assert [x['id'] for x in value['cases']] == ['owned-orphan', 'inactive-cache', 'active-cache']
    return value['cases']


def validate_answer(answer, case):
    expected = {'observed': case['observed'], 'recommendation': case['admitted_recommendation'],
                'cause': 'UNKNOWN' if case['unknowns'] else 'NOT_ESTABLISHED'}
    if type(answer) is not dict or answer != expected:
        raise ValueError('operations_catalog:invalid_closed_answer')
    return answer


def run(*, state, source, admission=None, config=None, acknowledgement=None, transport=None):
    """Default offline. External transport is admitted only by the exact bundle.

    Typed fixed facts have no raw prompt/log/identity values. This narrow boundary
    requires explicit owner/privacy acceptance; it does not qualify a redactor or
    permit free-text live conversations. No action is dispatched by any answer.
    """
    live = config is not None
    catalog_integrity = hashlib.sha256(CATALOG.read_bytes()).hexdigest()
    if live:
        expected = {'source': source, 'catalog_integrity': catalog_integrity,
            'owner_approved': True, 'fixed_nonpersonal_boundary_accepted': True,
            'processor_location_reviewed': True, 'native_provenance_and_network_passed': True,
            'fixture_identity_scope_accepted': True, 'requests': 3, 'retries': 0}
        if admission != expected or acknowledgement != ACK:
            raise ValueError('operations_catalog:live_not_admitted')
        if (set(config) != {'gateway_url', 'client_key', 'expires_at', 'model_alias', 'route'}
                or config['gateway_url'] != 'http://gateway.google-agent-demo.svc.cluster.local:4000'
                or config['model_alias'] != 'secure-financial-chat'
                or config['route'] != 'vertex_ai/gemini-2.5-flash@us-east1'):
            raise ValueError('operations_catalog:invalid_route')
        credential = ScopedCredential('infrastructure', config['client_key'], config['expires_at'])
    state.mkdir(mode=0o700)  # exclusive, no state reuse or automatic replay
    marker = state / 'execution.json'
    with marker.open('x') as out:
        out.write(json.dumps({'scope': 'fixed_synthetic_operations_reasoning', 'started': True}) + '\n')
        out.flush()
        os.fsync(out.fileno())
    results, attempts, begun = [], 0, time.monotonic()
    def audit(event):
        with (state / 'audit.jsonl').open('a') as out:
            out.write(json.dumps(event, sort_keys=True) + '\n');out.flush()
            os.fsync(out.fileno())
    for case in cases():
        if time.monotonic() - begun >= 30:
            results.append({'case': case['id'], 'status': 'BLOCKED', 'code': 'OVERALL_DEADLINE'});break
        if not live:
            results.append({'case': case['id'], 'status': 'OFFLINE_REFERENCE',
                'answer': validate_answer({'observed': case['observed'],
                    'recommendation': case['admitted_recommendation'],
                    'cause': 'UNKNOWN' if case['unknowns'] else 'NOT_ESTABLISHED'}, case)})
            continue
        try:
            key = credential.value('infrastructure')
            prompt = json.dumps(case, sort_keys=True)
            assert len(prompt.encode()) <= 4096
            audit({'case': case['id'], 'phase': 'admission', 'attempt': attempts + 1})
            attempts += 1  # failed content invocation attempts count; never retry
            response = (transport or _post_json)(config['gateway_url'] + '/chat/completions', {
                'model': config['model_alias'], 'stream': False, 'max_tokens': 256, 'temperature': 0,
                'messages': [{'role': 'system', 'content': 'Return only JSON observed, recommendation, cause. Copy observed. Recommend DO_NOT_MUTATE when active; otherwise REQUEST_OPERATOR_APPROVAL. Cause UNKNOWN if unknowns is nonempty, otherwise NOT_ESTABLISHED. You cannot approve or execute actions.'},
                             {'role': 'user', 'content': prompt}],
                'response_format': {'type': 'json_object'}}, 8,
                headers={'Authorization': 'Bearer ' + key})
            content = completion_content(response)
            if len(content.encode()) > 4096:
                raise ValueError
            answer = validate_answer(json.loads(content), case)
            if time.monotonic() - begun >= 30:
                raise ValueError
            audit({'case': case['id'], 'phase': 'outcome', 'status': 'PASS'})
            results.append({'case': case['id'], 'status': 'PASS', 'answer': answer})
        except Exception:
            results.append({'case': case['id'], 'status': 'BLOCKED', 'code': 'MODEL_OR_PROTOCOL_GATE_FAILED'});break
    receipt = {'scope': 'fixed_synthetic_operations_reasoning', 'mode': 'external_via_scoped_litellm' if live else 'offline_reference',
        'source': source, 'catalog_integrity': catalog_integrity, 'results': results,
        'model_attempts': attempts, 'max_model_attempts': 3, 'max_output_tokens': 768,
        'retries': 0, 'actions': 0, 'sdp_attempts': 0, 'live_ui_enabled': False}
    with (state / 'result.json').open('x') as out:
        out.write(json.dumps(receipt, indent=2) + '\n');out.flush()
        os.fsync(out.fileno())
    return receipt
