"""Presentation of the existing masking contract; this module does not change detection or policy."""
from runtime.phase3.trusted_runtime import SUPPORTED_ENTITIES

LABELS = {
    'EMAIL_ADDRESS': 'email addresses',
    'PHONE_NUMBER': 'phone numbers (supported Saudi and international formats)',
    'CREDIT_CARD': 'card numbers (supported formats and validation)',
    'IBAN_CODE': 'IBANs (Saudi formats and labelled international formats)',
    'SAUDI_BANK_ACCOUNT': 'labelled bank account numbers',
    'SAUDI_NATIONAL_ID': 'Saudi national ID numbers (supported labelled or contextual formats)',
    'SAUDI_RESIDENT_ID': 'Saudi residence ID numbers (supported labelled or contextual formats)',
    'SAUDI_VAT_ID': 'VAT/tax IDs (supported labelled or Saudi-shaped formats)',
}
SUMMARY = 'Supported identifier patterns are masked before model requests. Person names and passport numbers are not masked.'
LIMITS = 'Matching depends on format and context. It does not cover every spelling, format or kind of sensitive information.'
EXTRA = 'Some other labelled numeric IDs can be masked without a named category in the worker trace.'


def scope():
    if set(LABELS) != SUPPORTED_ENTITIES:
        raise ValueError('masking presentation differs from supported categories')
    return {'summary': SUMMARY, 'supported': [{'code': code, 'label': LABELS[code]} for code in sorted(SUPPORTED_ENTITIES)],
            'not_masked': ['person names', 'passport numbers'], 'limits': LIMITS, 'additional': EXTRA}


def explanation():
    value = scope()
    return 'Supported patterns: ' + '; '.join(row['label'] for row in value['supported']) + '. ' + LIMITS + ' ' + EXTRA
