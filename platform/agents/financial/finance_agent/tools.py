"""The Financial Agent's tools: read-only, strict arguments, always scoped to the signed-in user.

The model may only name a tool and give arguments; the code validates them, runs fixed SQL through the read-only role,
and returns plain data. Text that users typed (merchant names, notes) is untrusted: it is returned as data, and any
field that looks like an instruction is withheld before the model sees it.
"""
import re
import unicodedata

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


# Look-alike letters folded to Latin before matching (Greek and Cyrillic capitals and small letters that render like
# ASCII), so "Ιgnore" (Greek iota) or "ignоre" (Cyrillic o) is read as "ignore".
_CONFUSABLES = str.maketrans('ΑΒΕΖΗΙΚΜΝΟΡΤΥΧαεικνορτυχАВЕКМНОРСТХаеіјорсуххѕ', 'ABEZHIKMNOPTYXaeikvoptuxABEKMHOPCTXaeijopcyxxs')
_ARABIC_MARKS = re.compile('[\u064B-\u0652\u0640]')  # harakat and tatweel
# The platform-level indicators for user-entered text, in addition to the qualified assessor (runtime/agents/controls.py,
# hash-bound, unchanged). Found missing by the realistic-data review (RD-05): "ignore ALL PREVIOUS instructions",
# disregard/forget, role labels, Arabic with words between the verb and التعليمات, and the feminine/plural forms.
_INSTRUCTION_LIKE = re.compile('|'.join((
    r'\b(?:ignore|disregard|forget|override|bypass|skip)\b(?:\W+\w+){0,3}?\W+(?:instructions?|rules?|prompts?|polic(?:y|ies)'
    r'|guidelines?|directions?|constraints?)\b',
    r'\b(?:new|updated|real|actual) (?:system )?instructions\b',
    r'\bnote to (?:the )?(?:ai|assistant|model|agent|llm)\b',
    r'(?:^|[\s"{(\[])(?:system|assistant|developer)\s*:',
    r'"role"\s*:\s*"(?:system|assistant|developer)"',
    r'\byou are (?:now )?(?:an? |the )?(?:admin|administrator|root|developer|system|superuser)\b',
    '(?:تجاهل|تجاهلي|تجاهلوا|اتجاهل|انس|انسي|انسى|لا تتبع|لا تتبعي|لا تلتزم|تخط|تخطي|تخطى|تجاوز)'
    r'(?:\s+\S+){0,3}?\s+(?:ب|ل)?(?:ال)?(?:تعليمات|اوامر|قواعد|سياس)',
    r'ملاحظة\s+(?:لل|الي ال|الى ال)(?:مساعد|ذكاء|نموذج|وكيل)',
    r'انت الان\s+(?:ال)?(?:مدير|مسوول|مسؤول|ادمن|المشرف|مشرف)',
)), re.IGNORECASE)


def fold(text):
    """The text as a reader sees it: NFKC, no invisible format characters (zero-width, bidi marks, soft hyphen), look-alike
    letters as Latin, no Arabic harakat or tatweel, bare alef, lower case, single spaces."""
    text = unicodedata.normalize('NFKC', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf').translate(_CONFUSABLES)
    text = _ARABIC_MARKS.sub('', text).translate(str.maketrans('أإآى', 'اااي'))
    return ' '.join(text.lower().split())


def instruction_like(text):
    """True if user-entered text reads like an instruction to the model. A filter is never complete: the read-only tools,
    row-level security and the grounding checks hold whatever it misses."""
    if type(text) is not str or not text:
        return False
    folded = fold(text)
    return (any(_ASSESSOR.assess({'text': t}).outcome is not PromptInjectionOutcome.CLEAR for t in (text, folded))
            or _INSTRUCTION_LIKE.search(folded) is not None)


def untrusted(text):
    """User-entered text reaches the model only as data; instruction-like text is withheld."""
    return WITHHELD if instruction_like(text) else text


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
