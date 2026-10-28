"""Presentation of the existing masking contract; this module does not change detection or policy."""
from runtime.phase3.trusted_runtime import SUPPORTED_ENTITIES

LABELS = {  # short list labels; format details live in the redactor's pattern set, not in this presentation
    'EMAIL_ADDRESS': 'Email addresses',
    'PHONE_NUMBER': 'Phone numbers',
    'CREDIT_CARD': 'Payment card numbers',
    'IBAN_CODE': 'IBANs',
    'SAUDI_BANK_ACCOUNT': 'Bank account numbers (labelled)',
    'SAUDI_NATIONAL_ID': 'Saudi national IDs',
    'SAUDI_RESIDENT_ID': 'Saudi residence IDs',
    'SAUDI_VAT_ID': 'VAT / tax IDs',
}
SUMMARY = 'Supported identifier patterns are masked before model requests. Person names and passport numbers are not masked.'
LIMITS = 'Matching depends on format and context. It does not cover every spelling, format or kind of sensitive information.'
EXTRA = 'Some other labelled numeric IDs can be masked without a named category in the worker trace.'


AR_LABELS = {
    'EMAIL_ADDRESS': 'عناوين البريد الإلكتروني',
    'PHONE_NUMBER': 'أرقام الهاتف',
    'CREDIT_CARD': 'أرقام بطاقات الدفع',
    'IBAN_CODE': 'أرقام الآيبان',
    'SAUDI_BANK_ACCOUNT': 'أرقام الحسابات البنكية (المسبوقة بوصف)',
    'SAUDI_NATIONAL_ID': 'أرقام الهوية الوطنية السعودية',
    'SAUDI_RESIDENT_ID': 'أرقام الإقامة السعودية',
    'SAUDI_VAT_ID': 'الأرقام الضريبية',
}


def scope(language='en'):
    if set(LABELS) != SUPPORTED_ENTITIES or set(AR_LABELS) != SUPPORTED_ENTITIES:
        raise ValueError('masking presentation differs from supported categories')
    if language == 'ar':
        return {'summary': 'تُخفى أنماط المعرّفات المدعومة قبل إرسال الطلب إلى النموذج. لا تُخفى أسماء الأشخاص ولا أرقام جوازات السفر.',
                'supported': [{'code': code, 'label': AR_LABELS[code]} for code in sorted(SUPPORTED_ENTITIES)],
                'not_masked': ['أسماء الأشخاص', 'أرقام جوازات السفر'],
                'limits': 'تعتمد المطابقة على الصيغة والسياق، ولا تشمل كل كتابة أو صيغة أو نوع من المعلومات الحساسة.',
                'additional': 'قد تُخفى بعض المعرّفات الرقمية الأخرى المسبوقة بوصف دون فئة مسماة في أثر العامل.'}
    if language != 'en':
        raise ValueError('unsupported masking language')
    return {'summary': SUMMARY, 'supported': [{'code': code, 'label': LABELS[code]} for code in sorted(SUPPORTED_ENTITIES)],
            'not_masked': ['person names', 'passport numbers'], 'limits': LIMITS, 'additional': EXTRA}


def explanation():
    """One short list sentence plus the limit: "Masked: Email addresses · Phone numbers · …"."""
    value = scope()
    return 'Masked: ' + ' · '.join(row['label'] for row in value['supported']) + '. Not masked: person names, passport numbers. ' + LIMITS
