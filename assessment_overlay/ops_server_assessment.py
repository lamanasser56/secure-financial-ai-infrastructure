"""Disposable-assessment Ops entrypoint: deterministic explanation, zero SDP/model calls.

The assessment Secret must have blank gateway/redactor keys. Without this
entrypoint the normal server then has no explainer; with it, explanations use
only the fixed local stub. This file is an external runtime input to hash and
verify separately from the signed Ops image.
"""

import json
from pathlib import Path

from agent_platform.ops import server


def stub_explanation(_finding):
    return {
        'untrusted_text': 'Synthetic assessment explanation.',
        'untrusted_text_ar': 'شرح تجريبي للاختبار.',
        'source': 'assessment_stub',
    }


_normal_build = server.build


def assessment_build(config_dir=Path('/secrets/ops'), registry_dir=Path('/registry'),
                     observe_dir=Path('/observe')):
    config = json.loads((config_dir / 'ops.json').read_text(), object_pairs_hook=server.unique)
    if set(config) != {'api_key', 'approver_public_key', 'gateway_key', 'redactor_key', 'executor_key'}:
        raise SystemExit('assessment_ops:config_rejected')
    if config['gateway_key'] != '' or config['redactor_key'] != '':
        raise SystemExit('assessment_ops:real_explanation_keys_forbidden')
    agent, api_key = _normal_build(config_dir, registry_dir, observe_dir)
    if agent.explainer is not None:
        raise SystemExit('assessment_ops:unexpected_explainer')
    agent.explainer = stub_explanation
    return agent, api_key


if __name__ == '__main__':
    server.build = assessment_build
    server.main()
