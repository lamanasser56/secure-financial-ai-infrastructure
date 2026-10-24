"""Executed inside the retained redactor image root with synthetic mounts."""

import hashlib
import http.client
import json
from pathlib import Path
import threading
import sys

sys.path.insert(0, '/assessment')

from redactor_server import CompletionBudget, load_guard, load_platform
from sdp_guard import CompletedLedger
from seed_sdp import seed


platform = load_platform()
assert hashlib.sha256(Path('/app/evaluation/google-sdp-context/policy.json').read_bytes()).hexdigest() == platform.POLICY_HASH
assert load_guard().CompletedLedger is not None
seed('/assessment-state')


class Result:
    def __init__(self, text):
        self.text, self.categories = text, ()


class Redactor:
    def __init__(self):
        self.inputs = []

    def redact(self, text):
        self.inputs.append(text)
        return Result(text)


class Budget:
    def __init__(self, redactor):
        self.redactor = redactor

    def current(self):
        return self.redactor


redactor = Redactor()
keys = {'app': 'a' * 64, 'ops': 'b' * 64}
server = platform.Server(('127.0.0.1', 0), keys,
    CompletionBudget(Budget(redactor), CompletedLedger('/assessment-state/sdp-completions.json')),
    capacity=platform.Capacity(keys, per_client_window=25, global_window=25))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()


def call(text):
    client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
    client.request('POST', '/redact', json.dumps({'text': text}), {
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + 'a' * 64})
    response = client.getresponse()
    result = response.status, json.loads(response.read())
    client.close()
    return result


try:
    status, value = call('Call +1 202-555-0101 tomorrow.')
    assert status == 200 and value['text'] == 'Call PHONE_NUMBER tomorrow.'
    assert value['categories'] == ['PHONE_NUMBER']
    assert '+1 202-555-0101' not in redactor.inputs[0]
    for _ in range(19):
        assert call('synthetic no phone')[0] == 200
    assert call('synthetic no phone')[0] == 503
    assert len(redactor.inputs) == 20
    assert json.loads(Path('/assessment-state/sdp-completions.json').read_text())['completed'] == 20
finally:
    server.shutdown();server.server_close();thread.join(timeout=3)
print('CONTAINER REDACTOR PASS: inline phone, existing policy hash, 21st denied')
