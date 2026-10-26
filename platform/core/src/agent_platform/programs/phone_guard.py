"""Deterministic phone masking before the remote SDP inspection call.

The existing SDP policy remains in force for every other finding. This small
guard covers inline phone values that its line-anchored patterns miss. It is
packaged beside redactor_server.py in the signed redactor image.
"""

import re

_D = r"[0-9\u0660-\u0669\u06f0-\u06f9]"
_SEP = r"[ \t\u00a0\u2009\u202f\u2011\u2013.-]?"


def _digit(value):
    return "[" + value + chr(0x0660 + int(value)) + chr(0x06f0 + int(value)) + "]"


_SA_INTL = (
    r"\+" + _digit("9") + _SEP + _digit("6") + _SEP + _digit("6")
    + _SEP + _digit("5") + (_SEP + _D) * 8
)
_SA_LOCAL = _digit("0") + _SEP + _digit("5") + (_SEP + _D) * 8
_US = r"(?:\+1[ \t.-]?)?(?:\([2-9][0-9]{2}\)|[2-9][0-9]{2})[ \t.-]?[2-9][0-9]{2}[ \t.-]?[0-9]{4}"
_EDGE = r"A-Za-z0-9\u0660-\u0669\u06f0-\u06f9"
_PHONE = re.compile(r"(?<![" + _EDGE + r"+])(?:" + _SA_INTL + "|" + _SA_LOCAL + "|" + _US + r")(?![" + _EDGE + r"])")


def mask_phones(text):
    """Return (masked text, whether a supported phone was present)."""
    if type(text) is not str:
        raise ValueError("phone_guard:input")
    masked, count = _PHONE.subn("PHONE_NUMBER", text)
    return masked, bool(count)
