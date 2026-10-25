"""Run the console UI locally against stub ops data (no cluster, no secrets):

    PYTHONPATH=platform/core/src:platform/core/tests:. python platform/core/tests/console_stub.py [--port 8080] [--scenario ok|failing|down]

The real handler, the real rendered manifests and the real UI are served; only what the ops agent would answer is canned.
Scenarios: ok (healthy, redactor events seen), failing (no default-deny in a live list, a pod not ready), down (ops unreachable).
"""
import argparse
import copy
import time

from agent_platform import console
from runtime.agents.web import DemoServer

import test_console as t


class StubOperations:
    """The /api/operations side: an overview with one pending proposal; approvals are refused (no passphrase exists here)."""

    class controller:
        @staticmethod
        def budgets():
            return {}

    def __init__(self, now):
        self.now = now

    def handle(self, request):
        from runtime.agents.operations import OperationsBlocked
        if request.get('operation') == 'overview':
            n = self.now()
            # stub only: what an ops-agent explanation looks like on the board (real ones are model text, redacted, display only)
            return {'board': [{'target_id': 'apps.fault-demo', 'finding': 'READINESS_FAILING', 'desired': 1, 'available': 0, 'observe_only': False,
                               'explanation': '[stub] The pod is running but its readiness check keeps failing, so it receives no traffic. A restart is proposed.'},
                              {'target_id': 'platform.gateway', 'finding': 'HEALTHY', 'desired': 1, 'available': 1, 'observe_only': False},
                              *({'target_id': 'agent-financial.' + worker, 'finding': 'HEALTHY', 'desired': 1, 'available': 1, 'observe_only': True}
                                for worker in ('agent-u1', 'agent-u2', 'agent-u3'))],
                    'timeline': [{'stage': 'observed', 'target': 'apps.fault-demo', 'at': n - 240}, {'stage': 'diagnosed', 'target': 'apps.fault-demo', 'finding': 'READINESS_FAILING', 'at': n - 238},
                                 {'stage': 'proposed', 'target': 'apps.fault-demo', 'action': 'restart', 'at': n - 236}],
                    'pending': [{'request_id': 'r-1', 'target': 'apps.fault-demo', 'action': 'restart', 'finding': 'READINESS_FAILING'}], 'denials': []}
        raise OperationsBlocked('APPROVAL_DENIED')


def scenario(name, now):
    answers = t.ops_answers()
    shift = now - t.NOW
    for finding in answers['/v1/snapshot']['findings'].values():
        finding['facts']['observed_at'] += shift
    for e in answers['/v1/snapshot']['timeline'] + answers['/v1/activity']['events']:
        e['at'] += shift
    # The merged RBAC lets the ops agent list NetworkPolicies in agent namespaces too (Part D), so the stub reads them all.
    answers['/v1/posture'] = t.posture.check(t.KubeStub(), ['apps', 'platform', 'agent-financial', 'agent-platform-guide'])
    if name == 'failing':
        weak = t.posture.check(t.KubeStub(), ['agent-financial', 'apps', 'platform'])
        weak['network']['agent-financial'] = [p for p in weak['network']['agent-financial'] if p['name'] != 'default-deny']
        answers['/v1/posture'] = weak
        answers['/v1/snapshot']['findings']['agent-platform-guide.agent']['facts'].update(pods_ready=0)
        answers['/v1/snapshot']['findings']['agent-platform-guide.agent']['finding'] = 'READINESS_FAILING'
    if name == 'down':
        return {}
    return answers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--scenario', default='ok', choices=('ok', 'failing', 'down'))
    parser.add_argument('--live-attacks', help='a sanitized results file to serve as the live run (as if mounted from the ConfigMap)')
    args = parser.parse_args()
    server = DemoServer(('127.0.0.1', args.port), agents={}, composition='stub', operations=StubOperations(time.time))

    def ops(path):
        answers = scenario(args.scenario, time.time())
        if path not in answers:
            raise OSError('unreachable')
        return answers[path]
    console.attach(server, ops)
    if args.live_attacks:
        server.console.live_attacks = __import__('pathlib').Path(args.live_attacks)
    print('console stub (%s): http://127.0.0.1:%d/' % (args.scenario, args.port), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
