"""Trusted user authentication + data broker. Deploy in apps, never inside an onboarded agent namespace."""
import json
from pathlib import Path
import threading

from agent_platform.boundary_http import Server as BrokerServer, request_json
from agent_platform.data_capability import CapabilityIssuer
from finance_agent.agent import Blocked, Limits
from finance_agent.auth import LoginThrottle, Sessions
from finance_agent.data_broker import DataBroker
from finance_agent.server import Handler, Server, serve
from finance_agent.store import Store


class Forwarder:
    def __init__(self, issuer, routes, *, dispatch=request_json):
        self.issuer, self.routes, self.dispatch = issuer, dict(routes), dispatch
        if any(set(route) != {'agent', 'key', 'url'} for route in routes.values()):
            raise ValueError('worker routes must be explicitly bound to authenticated users')
        self.limits = Limits()

    def ask(self, user, question, language):
        token = claims = None
        try:
            self.limits.check(user)
            route = self.routes[user]
            token, claims = self.issuer.issue(user, route['agent'])
            value, _ = self.dispatch(route['url'], route['key'],
                                     {'capability': token, 'question': question, 'language': language}, timeout=60)
            return value
        except Blocked as error:
            return {'status': 'blocked', 'reason': error.reason, 'limits': self.limits.remaining(user)}
        except Exception:
            return {'status': 'blocked', 'reason': 'worker_unavailable', 'limits': self.limits.remaining(user)}
        finally:
            if claims:
                self.issuer.revoke(claims)

    def _user_ref(self, user):
        # Frontdoor cookie key never reaches the worker; the data broker emits its own identity reference.
        import hashlib
        return hashlib.sha256(user.encode()).hexdigest()[:16]

    def forget(self, user):
        claims = None
        try:
            route = self.routes[user]
            token, claims = self.issuer.issue(user, route['agent'])
            self.dispatch(route['url'].rsplit('/', 1)[0] + '/forget', route['key'], {'capability': token})
        except Exception:
            pass  # Cookie revocation remains effective even if the separate worker is unavailable.
        finally:
            if claims:
                self.issuer.revoke(claims)


def main():
    config = json.loads(Path('/secrets/frontdoor/frontdoor.json').read_text())
    issuer = CapabilityIssuer(config['capability_private_key'], config['capability_public_key'])
    store = Store(config['web_db_url'], config['read_db_url'])
    key = bytes.fromhex(config['session_key'])
    server = Server(('0.0.0.0', 8081), Handler)
    server.hosts, server.store = {'127.0.0.1:8081'}, store
    server.sessions, server.throttle = Sessions(key), LoginThrottle()
    server.agent = Forwarder(issuer, config['routes'])
    broker = BrokerServer(('0.0.0.0', 8082), DataBroker(store, issuer, config['broker_clients'], user_bindings=config['user_bindings'], audit_key=key))
    thread = threading.Thread(target=broker.serve_forever, daemon=True)
    thread.start()
    try:
        serve(server)
    finally:
        broker.shutdown()
        broker.server_close()
        thread.join(5)


if __name__ == '__main__':
    main()
