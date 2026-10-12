"""The Financial Agent's tools: read-only, strict arguments, always scoped to the signed-in user.

The model may only name a tool and give arguments; the code validates them, runs fixed SQL through the read-only role,
and returns plain data. Text that users typed (merchant names, notes) is untrusted: it is returned as data, and any
field that looks like an instruction is withheld before the model sees it.
"""
from runtime.agents.controls import BoundedInjectionAssessor
from runtime.phase4.prompt_injection import PromptInjectionOutcome

from finance_agent.store import CATEGORIES, InvalidExpense, month_range, row

WITHHELD = '[withheld: looked like an instruction]'
_ASSESSOR = BoundedInjectionAssessor()


class ToolRejected(ValueError):
    pass


def _args(args, allowed, required):
    if type(args) is not dict or set(args) - set(allowed) or not set(required) <= set(args):
        raise ToolRejected('arguments: allowed %s, required %s' % (sorted(allowed), sorted(required)))
    try:
        return month_range(args['month'])
    except InvalidExpense as error:
        raise ToolRejected(str(error)) from None


def untrusted(text):
    """User-entered text reaches the model only as data; instruction-like text is withheld."""
    if _ASSESSOR.assess({'text': text}).outcome is not PromptInjectionOutcome.CLEAR:
        return WITHHELD
    return text


def monthly_total(store, user_id, args):
    start, end = _args(args, {'month'}, {'month'})
    total, count = store.read(user_id, 'SELECT coalesce(sum(amount_minor), 0), count(*) FROM finance.expenses '
                                       'WHERE spent_on >= %s AND spent_on < %s', (start, end))[0]
    return {'month': args['month'], 'total_minor': int(total), 'count': int(count), 'currency': 'SAR'}


def spending_by_category(store, user_id, args):
    start, end = _args(args, {'month'}, {'month'})
    rows = store.read(user_id, 'SELECT category, sum(amount_minor), count(*) FROM finance.expenses '
                               'WHERE spent_on >= %s AND spent_on < %s GROUP BY category ORDER BY 2 DESC', (start, end))
    return {'month': args['month'], 'currency': 'SAR',
            'categories': [{'category': c, 'total_minor': int(t), 'count': int(n)} for c, t, n in rows]}


def find_transactions(store, user_id, args):
    """Transaction-level lookup: the signed-in user's own expenses in one month, optionally filtered."""
    start, end = _args(args, {'month', 'category', 'merchant_contains', 'limit'}, {'month'})
    category, needle, limit = args.get('category'), args.get('merchant_contains'), args.get('limit', 10)
    if category is not None and category not in CATEGORIES:
        raise ToolRejected('category must be one of ' + ', '.join(CATEGORIES))
    if needle is not None and (type(needle) is not str or not 1 <= len(needle) <= 30):
        raise ToolRejected('merchant_contains: 1-30 characters')
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ToolRejected('limit: 1-10')
    escaped = None if needle is None else needle.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')  # literal match
    records = store.read(
        user_id,
        'SELECT id, spent_on, merchant, category, amount_minor, note FROM finance.expenses '
        'WHERE spent_on >= %s AND spent_on < %s AND (%s::text IS NULL OR category = %s) '
        "AND (%s::text IS NULL OR merchant ILIKE '%%' || %s || '%%') ORDER BY spent_on, id LIMIT %s",
        (start, end, category, category, needle, escaped, limit + 1))
    found = [row(r) for r in records]
    for item in found:
        item['merchant'], item['note'] = untrusted(item['merchant']), untrusted(item['note'])
    return {'month': args['month'], 'currency': 'SAR', 'transactions': found[:limit], 'more_exist': len(found) > limit}


TOOLS = {
    'monthly_total': (monthly_total, 'Total spent and number of expenses in one month. args: {"month": "YYYY-MM"}'),
    'spending_by_category': (spending_by_category, 'Spending per category in one month. args: {"month": "YYYY-MM"}'),
    'find_transactions': (find_transactions, 'Individual expenses in one month (id, date, merchant, category, amount, '
                          'note). args: {"month": "YYYY-MM", "category"?: one of ' + '|'.join(CATEGORIES)
                          + ', "merchant_contains"?: text, "limit"?: 1-10}'),
}
READ_ONLY = frozenset(TOOLS)  # a test fails if any write-shaped tool is ever registered
