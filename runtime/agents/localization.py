"""Approved display language and fixture translations, never model authority."""

from functools import lru_cache
import json
from runtime.agents.schemas import ROOT, read_fixed


@lru_cache(maxsize=1)
def catalog():
    return json.loads(read_fixed(ROOT / "demo/i18n.json", 32768))


def text(key, language="en", **values):
    if language not in {"en", "ar"}:
        raise ValueError("agent:invalid_language")
    return catalog()[language][key].format(**values)


def fixture_text(value, language="en"):
    if value not in catalog()["fixture_ar"]:
        raise ValueError("agent:unqualified_fixture_translation")
    if language == "en":
        return value
    if language != "ar" or value not in catalog()["fixture_ar"]:
        raise ValueError("agent:unqualified_fixture_translation")
    return catalog()["fixture_ar"][value]
