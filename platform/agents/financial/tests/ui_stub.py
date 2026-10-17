"""Run the Financial Agent UI locally with a scripted model and an in-memory store (no cluster, no database, no secrets):

    PYTHONPATH=platform/core/src:platform/agents/financial:platform/agents/financial/tests:. python platform/agents/financial/tests/ui_stub.py [--port 8081]

Sign in as demo / demo-password-1. The real server, sessions, agent, grounding and trace are used; the model's replies are scripted.
"""
import argparse
import itertools
import uuid

from finance_agent import server
from finance_agent.auth import hash_password

from test_finance_agent import Redactor, Store
from test_trace import TOOL, Costed

ANSWER = {'action': 'answer', 'text': 'You spent 245.00 SAR in 2026-10.'}  # the October total of ROWS below, so the grounding check passes

USER = str(uuid.uuid4())
ROWS = {USER: [(1, '2026-10-02', 'Cafe Nova', 'food', 2450, ''), (2, '2026-10-05', 'Metro card', 'transport', 6000, ''),
               (3, '2026-10-11', 'Book shop', 'shopping', 12000, ''), (4, '2026-10-19', 'Pharmacy', 'health', 4050, '')]}


class StubStore(Store):
    def __init__(self):
        super().__init__(ROWS)
        self.account = {'id': USER, 'display_name': 'Demo', 'password_hash': hash_password('demo-password-1')}

    def user(self, username):
        return self.account if username == 'demo' else None

    def list_expenses(self, user_id, month):
        return [{'id': r[0], 'date': r[1], 'merchant': r[2], 'category': r[3], 'amount_minor': r[4], 'note': r[5]}
                for r in self.rows.get(user_id, []) if r[1].startswith(month)]

    def add_expense(self, user_id, entry):
        rows = self.rows.setdefault(user_id, [])
        rows.append((len(rows) + 1, entry['spent_on'], entry['merchant'], entry['category'], int(round(float(entry['amount']) * 100)), entry.get('note', '')))
        return len(rows)


class Cycling(Costed):
    """Scripted model: a tool step then a grounded answer, for every question."""

    def __init__(self):
        super().__init__()
        self.replies = itertools.cycle([TOOL, ANSWER])

    def complete(self, messages):
        self.prompts.append(messages[1]['content'])
        import json
        return json.dumps(next(self.replies)), 100, {'model': self.resolved, 'cost_usd': self.cost}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8081)
    args = parser.parse_args()
    httpd = server.ThreadingHTTPServer(('127.0.0.1', args.port), server.Handler)
    httpd.daemon_threads = True
    httpd.hosts = {'127.0.0.1:%d' % args.port}
    httpd.store, httpd.sessions, httpd.throttle, httpd.agent = server.build({'session_key': 'ab' * 32}, store=StubStore(), redactor=Redactor(), gateway=Cycling())
    print('financial UI stub: http://127.0.0.1:%d/  (demo / demo-password-1)' % args.port, flush=True)
    httpd.serve_forever()


if __name__ == '__main__':
    main()
