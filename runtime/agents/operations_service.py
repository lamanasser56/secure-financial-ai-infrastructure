"""Closed UI operations dispatch. Browser and model cannot register host targets."""
from runtime.agents.operations import OperationsBlocked
from runtime.agents.operations_security import read_subject
import json


def decode_request(body):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise OperationsBlocked('INVALID_REQUEST')
            value[key] = item
        return value
    return json.loads(body, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(OperationsBlocked('INVALID_REQUEST')))


class OperationsService:
    def __init__(self, controller, security=None, *, financial_url='http://127.0.0.1:8768'):
        self.controller, self.security = controller, security
        self.financial_url = financial_url

    def handle(self, request):
        fields = {'overview': set(), 'observe': {'target_id'},
                  'diagnose': {'target_id', 'evidence_id'},
                  'propose': {'target_id', 'action', 'evidence_id'},
                  'approve': {'request_id', 'operator_secret'},
                  'execute': {'request_id', 'approval_id'},
                  'explain': {'target_id'}, 'security': set()}
        if type(request) is not dict:
            raise OperationsBlocked('INVALID_REQUEST')
        operation = request.get('operation')
        if operation not in fields or set(request) != fields[operation] | {'operation'}:
            raise OperationsBlocked('INVALID_REQUEST')
        if any(type(v) is not str or not 0 < len(v.encode()) <= 512 for v in request.values()):
            raise OperationsBlocked('INVALID_REQUEST')
        c = self.controller
        if operation == 'overview':
            admitted = []
            for key, target in c.targets.items():
                try:
                    c._principal(key, 'monitor')
                    admitted.append({'target_id': key, 'mutable': target.mutable,
                                     'kind': 'service' if hasattr(target, 'adapter') else 'stack' if hasattr(target, 'members') else 'cache'})
                except OperationsBlocked:
                    continue
            return {'targets': [{'target_id': k, 'mutable': v.mutable,
                                 'kind': 'service' if hasattr(v, 'adapter') else 'stack' if hasattr(v, 'members') else 'cache'}
                               for k, v in c.targets.items() if any(x['target_id'] == k for x in admitted)],
                    'budgets': c.budgets(), 'recent': c.reports[-8:],
                    'identity_authority': 'local_fixture_operator', 'financial_ui': self.financial_url,
                    'model_boundary': 'disabled' if c.model is None else getattr(c.model,'mode','local_stub_simulated_redaction')}
        if operation == 'security':
            if self.security is None:
                return {'vulnerability_policy': 'unknown', 'code': 'NO_REGISTERED_EVIDENCE',
                        'allow_decision': False}
            try:
                return read_subject(self.security)
            except Exception:
                return {'vulnerability_policy': 'deny', 'code': 'INVALID_SECURITY_EVIDENCE',
                        'allow_decision': False}
        if operation == 'observe':
            return c.observe(request['target_id'])
        if operation == 'diagnose':
            return c.diagnose(request['target_id'], request['evidence_id'])
        if operation == 'propose':
            return c.propose(request['target_id'], request['action'], request['evidence_id'])
        if operation == 'approve':
            return c.approve(request['request_id'], request['operator_secret'])
        if operation == 'execute':
            return c.execute(request['request_id'], request['approval_id'])
        return c.explain(request['target_id'])
