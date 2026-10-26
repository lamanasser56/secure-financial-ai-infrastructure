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


AR_LABELS = {
    'EMAIL_ADDRESS': 'عناوين البريد الإلكتروني',
    'PHONE_NUMBER': 'أرقام الهاتف بصيغ سعودية ودولية مدعومة',
    'CREDIT_CARD': 'أرقام البطاقات بالصيغ والتحقق المدعومين',
    'IBAN_CODE': 'أرقام آيبان السعودية والدولية المسبوقة بوصف',
    'SAUDI_BANK_ACCOUNT': 'أرقام الحسابات المصرفية المسبوقة بوصف',
    'SAUDI_NATIONAL_ID': 'أرقام الهوية الوطنية السعودية ضمن الصيغ والأوصاف المدعومة',
    'SAUDI_RESIDENT_ID': 'أرقام الإقامة السعودية ضمن الصيغ والأوصاف المدعومة',
    'SAUDI_VAT_ID': 'الأرقام الضريبية المسبوقة بوصف أو المطابقة للصيغة السعودية',
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
    value = scope()
    return 'Supported patterns: ' + '; '.join(row['label'] for row in value['supported']) + '. ' + LIMITS + ' ' + EXTRA
