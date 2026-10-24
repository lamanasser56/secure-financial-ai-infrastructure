"""Data tools run in the trusted frontdoor Pod; worker input never selects a database user or SQL statement."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import hmac

from agent_platform import audit
from agent_platform.boundary_http import Clients, Rejected, request_json
from finance_agent.tools import TOOLS, ToolRejected

URL = 'http://financial-frontdoor.apps.svc.cluster.local:8082/tools'


class DataBroker:
    def __init__(self, store, issuer, keys, *, user_bindings, audit_key):
        if set(keys) != set(user_bindings) or len(set(user_bindings.values())) != len(user_bindings):
            raise ValueError('each broker principal must bind exactly one separate user')
        self.store, self.issuer, self.clients, self.audit_key = store, issuer, Clients(keys), audit_key
        self.user_bindings = dict(user_bindings)

    def handle(self, path, authorization, body):
        with self.clients.admit(authorization) as agent:
            if (path != '/tools' or type(body) is not dict or set(body) != {'capability', 'tool', 'args'}
                    or type(body['tool']) is not str or body['tool'] not in TOOLS or type(body['args']) is not dict):
                raise Rejected('TOOL_REJECTED', 400)
            claims = self.issuer.verify(body['capability'], agent)
            if claims['user'] != self.user_bindings[agent]:
                raise Rejected('USER_BINDING_REJECTED')
            if body['tool'] not in claims['tools']:
                raise Rejected('TOOL_REJECTED')
            outcome = 'FAILED'
            try:
                result = TOOLS[body['tool']][0](self.store, claims['user'], body['args'])
                outcome = 'READ'
                return result, {}
            except ToolRejected:
                raise Rejected('ARGUMENTS_REJECTED', 400) from None
            finally:
                ref = hmac.new(self.audit_key, claims['user'].encode(), hashlib.sha256).hexdigest()[:16]
                audit.emit('broker_tool', 'data-broker', caller=agent, user_ref=ref, request_id=claims['nonce'],
                           tool_id=body['tool'], outcome=outcome)


class RemoteStore:
    """Worker-side transport only: no DB driver, connection credentials or identity signing key."""
    def __init__(self, key, *, dispatch=request_json):
        self.key, self.dispatch, self.context = key, dispatch, ContextVar('finance_capability')

    @contextmanager
    def scope(self, token, claims):
        binding = self.context.set((token, claims))
        try:
            yield
        finally:
            self.context.reset(binding)

    def invoke_tool(self, name, user, args):
        token, claims = self.context.get()
        if claims['user'] != user:
            raise ToolRejected('user mismatch')
        result, _ = self.dispatch(URL, self.key, {'capability': token, 'tool': name, 'args': args})
        return result
