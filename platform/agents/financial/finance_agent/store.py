"""Database access for the Financial Agent (platform/core/database/finance.sql).

Two roles, two connections:
- `web` (finance_web): sign-in lookup, then add and list the signed-in user's own expenses;
- `agent` (finance_agent): the agent's read-only tools.
Every scoped call opens a transaction and sets `finance.user_id` from the verified session (SET LOCAL semantics), so
row-level security decides what is visible. No SQL is ever built from user or model text.
"""
from contextlib import contextmanager
import datetime
import re

CATEGORIES = ('food', 'transport', 'shopping', 'bills', 'health', 'travel', 'other')
MONTH = re.compile(r'20[2-3][0-9]-(0[1-9]|1[0-2])')
MAX_AMOUNT_MINOR = 10_000_000  # 100,000.00 SAR


class InvalidExpense(ValueError):
    pass


def month_range(month):
    if type(month) is not str or not MONTH.fullmatch(month):
        raise InvalidExpense('month must be YYYY-MM')
    start = datetime.date(int(month[:4]), int(month[5:]), 1)
    end = datetime.date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, end


def clean_text(value, limit, field, *, required):
    if type(value) is not str:
        raise InvalidExpense(field + ' must be text')
    value = ' '.join(value.split())  # no control characters or line breaks survive
    if (required and not value) or len(value) > limit:
        raise InvalidExpense('%s: %s%d characters' % (field, '1-' if required else 'at most ', limit))
    return value


def validate_expense(entry):
    if type(entry) is not dict or set(entry) - {'spent_on', 'merchant', 'category', 'amount', 'note'} or \
            not {'spent_on', 'merchant', 'category', 'amount'} <= set(entry):
        raise InvalidExpense('fields: spent_on, merchant, category, amount, note (optional)')
    try:
        spent_on = datetime.date.fromisoformat(entry['spent_on'])
    except (TypeError, ValueError):
        raise InvalidExpense('spent_on must be YYYY-MM-DD') from None
    if not datetime.date(2020, 1, 1) <= spent_on <= datetime.date(2035, 12, 31):
        raise InvalidExpense('spent_on out of range')
    if entry['category'] not in CATEGORIES:
        raise InvalidExpense('category must be one of ' + ', '.join(CATEGORIES))
    amount = entry['amount']
    if type(amount) is str and re.fullmatch(r'[0-9]{1,6}(\.[0-9]{1,2})?', amount):
        whole, _, cents = amount.partition('.')
        amount_minor = int(whole) * 100 + int((cents + '00')[:2])
    else:
        raise InvalidExpense('amount must be a positive number with up to 2 decimals, e.g. "24.50"')
    if not 0 < amount_minor <= MAX_AMOUNT_MINOR:
        raise InvalidExpense('amount must be above 0 and at most 100000.00')
    return {'spent_on': spent_on, 'merchant': clean_text(entry['merchant'], 60, 'merchant', required=True),
            'category': entry['category'], 'amount_minor': amount_minor,
            'note': clean_text(entry.get('note', ''), 200, 'note', required=False)}


def row(record):
    expense_id, spent_on, merchant, category, amount_minor, note = record
    return {'id': expense_id, 'date': spent_on.isoformat(), 'merchant': merchant, 'category': category,
            'amount_minor': amount_minor, 'note': note}


class Store:
    def __init__(self, web_dsn, agent_dsn, *, connect=None):
        import psycopg
        self._connect = connect or (lambda dsn: psycopg.connect(dsn, connect_timeout=5))
        self._web, self._agent = web_dsn, agent_dsn

    @contextmanager
    def _scoped(self, dsn, user_id):
        with self._connect(dsn) as db:  # psycopg: one transaction, committed on success
            db.execute("SELECT set_config('finance.user_id', %s, true)", (user_id,))
            yield db

    def user(self, username):
        if type(username) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{2,19}', username):
            return None
        with self._connect(self._web) as db:
            found = db.execute('SELECT id::text, display_name, password_hash FROM finance.login_lookup(%s)', (username,)).fetchone()
        return None if found is None else {'id': found[0], 'display_name': found[1], 'password_hash': found[2]}

    def add_expense(self, user_id, entry):
        e = validate_expense(entry)
        with self._scoped(self._web, user_id) as db:
            new_id = db.execute('INSERT INTO finance.expenses(spent_on, merchant, category, amount_minor, note) '
                                'VALUES (%s, %s, %s, %s, %s) RETURNING id',
                                (e['spent_on'], e['merchant'], e['category'], e['amount_minor'], e['note'])).fetchone()[0]
        return new_id

    def list_expenses(self, user_id, month):
        start, end = month_range(month)
        with self._scoped(self._web, user_id) as db:
            records = db.execute('SELECT id, spent_on, merchant, category, amount_minor, note FROM finance.expenses '
                                 'WHERE spent_on >= %s AND spent_on < %s ORDER BY spent_on DESC, id DESC LIMIT 200',
                                 (start, end)).fetchall()
        return [row(r) for r in records]

    def read(self, user_id, statement, params):
        """Agent tools only: the read-only role, scoped to the signed-in user by row-level security."""
        with self._scoped(self._agent, user_id) as db:
            return db.execute(statement, params).fetchall()
