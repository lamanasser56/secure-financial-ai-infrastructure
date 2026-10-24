"""Executed inside the qualified Ops image root with synthetic mount."""

import json
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, '/app/platform/src')
sys.path.insert(0, '/assessment')
import ops_server_assessment as assessment

root = Path('/assessment-state')
root.mkdir(exist_ok=True)
config = {'api_key': 'synthetic', 'approver_public_key': 'synthetic',
          'gateway_key': '', 'redactor_key': '', 'executor_key': 'synthetic'}
(root / 'ops.json').write_text(json.dumps(config))
agent = SimpleNamespace(explainer=None)
assessment._normal_build = lambda *args: (agent, 'synthetic')
created, key = assessment.assessment_build(root, root, root)
assert created is agent and key == 'synthetic'
assert created.explainer({'untrusted': 'must not appear'})['source'] == 'assessment_stub'
assert 'must not appear' not in created.explainer({'untrusted': 'must not appear'})['untrusted_text']
config['redactor_key'] = 'would-call-real-sdp'
(root / 'ops.json').write_text(json.dumps(config))
try:
    assessment.assessment_build(root, root, root)
except SystemExit:
    pass
else:
    raise AssertionError('real redactor key accepted')
print('CONTAINER OPS PASS: fixed stub, real redactor key rejected')
