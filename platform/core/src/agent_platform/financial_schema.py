"""Financial form/data contract, shared by bootstrap, validation and authenticated UI metadata."""

DEMO_MONTH = '2026-10'  # Declared synthetic recording period; never inferred from the browser clock.
CATEGORY_LABELS = (
    ('food', 'Food', 'طعام'),
    ('transport', 'Transport', 'نقل'),
    ('shopping', 'Shopping', 'تسوق'),
    ('bills', 'Bills', 'فواتير'),
    ('subscriptions', 'Subscriptions', 'اشتراكات'),
    ('health', 'Health', 'صحة'),
    ('travel', 'Travel', 'سفر'),
    ('other', 'Other', 'أخرى'),
)
CATEGORIES = tuple(code for code, _, _ in CATEGORY_LABELS)
# Only fixed developer-owned codes enter DDL; no user, model or translation text is interpolated.
CATEGORY_CONSTRAINT = ('ALTER TABLE finance.expenses DROP CONSTRAINT IF EXISTS expenses_category_check, '
                       'ADD CONSTRAINT expenses_category_check CHECK (category IN ('
                       + ', '.join("'%s'" % code for code in CATEGORIES) + '))')


def metadata():
    return {'demo_month': DEMO_MONTH,
            'categories': [{'code': code, 'labels': {'en': en, 'ar': ar}} for code, en, ar in CATEGORY_LABELS]}
