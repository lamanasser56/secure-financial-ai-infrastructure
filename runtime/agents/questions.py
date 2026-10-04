"""Limited deterministic offline grammar; not a general language model.

The actual question remains in the validated/redacted runtime prompt.
Only complete supported question forms or explicit clarification replies are
recognized. An unrelated question is never mapped to a default scenario.
This module selects demo scope; existing governance authorizes every tool.
"""

from dataclasses import dataclass
import re

SCENARIOS = ("archive-export", "docker-config", "cluster-version")
MONTHS = (
    ("january", "يناير"),
    ("february", "فبراير"),
    ("march", "مارس"),
    ("april", "ابريل"),
    ("may", "مايو"),
    ("june", "يونيو"),
    ("july", "يوليو"),
    ("august", "اغسطس"),
    ("september", "سبتمبر"),
    ("october", "اكتوبر"),
    ("november", "نوفمبر"),
    ("december", "ديسمبر"),
)
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
BIDI_CONTROLS = re.compile(r"[\u202a-\u202e\u2066-\u2069]")


def normalized(value):
    value = value.lower().translate(DIGITS)
    value = re.sub(r"[\u064b-\u065f\u0670]", "", value)
    value = value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا"}))
    return re.sub(r"\s+", " ", value).strip(" .?!؟\n\t")


@dataclass(frozen=True)
class Scope:
    status: str
    reason_code: str | None = None
    period: str | None = None
    scenario_id: str | None = None
    intent: str | None = None


def periods_and_remainder(value):
    dates = re.findall(r"(?<!\d)(20\d{2}-(?:0[1-9]|1[0-2]))(?!\d)", value)
    remainder = re.sub(r"(?<!\d)20\d{2}-(?:0[1-9]|1[0-2])(?!\d)", " ", value)
    years = re.findall(r"\b20\d{2}\b", remainder)
    named = []
    for number, names in enumerate(MONTHS, 1):
        for name in names:
            if re.search(r"(?<!\w)" + name + r"(?!\w)", remainder):
                named.append(number)
                remainder = re.sub(r"(?<!\w)" + name + r"(?!\w)", " ", remainder)
    if named and years:
        dates.extend(f"{year}-{month:02d}" for year in years for month in named)
        remainder = re.sub(r"\b20\d{2}\b", " ", remainder)
    return sorted(set(dates)), normalized(remainder)


def financial_scope(message, selected_period, previous):
    value = normalized(message)
    periods, remainder = periods_and_remainder(value)
    # Only grammatical date replies can continue a financial clarification.
    date_reply = (
        bool(periods)
        and re.fullmatch(
            r"(?:(?:for|in|during|please|use|and|or|what about|في|عن|او|و|استخدم|من فضلك|ماذا عن)\s*)*",
            remainder,
        )
        is not None
    )
    supported = (
        re.fullmatch(
            r"(?:how much did i spend|what did i spend)(?: (?:in|during|for))*",
            remainder,
        )
        is not None
        or value in {"analyze synthetic expenses", "حلل المصاريف الاصطناعية"}
        or re.fullmatch(
            r"(?:(?:show|summarize|analyse|analyze|what are|what were|how much are|give me|calculate) )?"
            r"(?:(?:my|the|synthetic|tenant-scoped|total) )*"
            r"(?:expenses|expense totals|expense summary|expense totals and categories|expense categories|spending)"
            r"(?: (?:and categories|by category|totals|summary|categories))*"
            r"(?: (?:for|in|during|and|or|last month|this month))*",
            remainder,
        )
        is not None
        or re.fullmatch(
            r"(?:(?:كم|ما|اعرض|حلل|لخص|اظهر) )?"
            r"(?:(?:اجمالي|مجموع|ملخص|فئات) )*"
            r"(?:مصاريفي|مصروفاتي|المصاريف|المصروفات|مصاريف|النفقات|الانفاق|المصاريف الاصطناعية)"
            r"(?: (?:وفئاتها|حسب الفئة|حسب الفئات|واجمالياتها))*"
            r"(?: (?:في|عن|خلال|او|و|الشهر الماضي|هذا الشهر))*",
            remainder,
        )
        is not None
    )
    if not supported and not (date_reply and previous.get("intent") == "financial"):
        return Scope("refused", "offline_unsupported")
    if selected_period is not None:
        periods = sorted(set(periods + [selected_period]))
    if len(periods) != 1:
        return Scope("clarification_required", "period_required", intent="financial")
    return Scope("ready", period=periods[0], intent="financial")


TOPICS = {
    "archive-export": r"(?:docker archive export|archive export|تصدير صورة docker|تصدير ارشيف docker)",
    "docker-config": r"(?:docker configuration lifecycle|docker configuration|docker config|دورة اعداد docker|اعداد docker)",
    "cluster-version": r"(?:gke cluster version contract|gke cluster version|cluster version contract|عقد اصدار عنقود gke|اصدار عنقود gke)",
}


def infrastructure_scope(message, selected_source, previous):
    value = normalized(message)
    found = []
    for source, topic in TOPICS.items():
        if re.fullmatch(
            r"(?:why did|why does|explain|diagnose|what caused|how should i fix|how do i fix|how can i fix|what does the runbook say about) "
            r"(?:the |this )?" + topic + r"(?: fail| failure| error| problem)?",
            value,
        ) or re.fullmatch(
            r"(?:لماذا فشل|لماذا فشلت|لماذا يفشل|اشرح|شخص|كيف اصلح|ما سبب فشل|ماذا يقول دليل التشغيل عن) "
            + topic,
            value,
        ):
            found.append(source)
    if found:
        if len(found) != 1 or selected_source not in {None, found[0]}:
            return Scope(
                "clarification_required", "evidence_required", intent="infrastructure"
            )
        return Scope("ready", scenario_id=found[0], intent="infrastructure")
    reply = value.removeprefix("use ").removeprefix("استخدم ")
    if previous.get("intent") == "infrastructure":
        for source, topic in TOPICS.items():
            if reply == source or re.fullmatch(topic, reply):
                return Scope("ready", scenario_id=source, intent="infrastructure")
        if value in {"use this source", "استخدم هذا المصدر"} and selected_source:
            return Scope("ready", scenario_id=selected_source, intent="infrastructure")
    generic = value in {
        "diagnose this synthetic infrastructure failure",
        "شخص فشل البنية التحتية الاصطناعي",
        "why did the release fail",
        "diagnose the release failure",
        "explain this infrastructure failure",
        "لماذا فشل الاصدار",
        "شخص فشل البنية التحتية",
        "اشرح فشل البنية التحتية",
    }
    if generic:
        if selected_source is None:
            return Scope(
                "clarification_required", "evidence_required", intent="infrastructure"
            )
        return Scope("ready", scenario_id=selected_source, intent="infrastructure")
    if re.fullmatch(
        r"(?:diagnose|explain|show|شخص|اشرح|اعرض) (?:evidence|source|الدليل|المصدر) .{1,120}",
        value,
    ):
        return Scope("unavailable", "evidence_unavailable")
    return Scope("refused", "offline_unsupported")


def select_scope(profile, message, period=None, scenario_id=None, previous=None):
    if BIDI_CONTROLS.search(message) or any(
        ord(c) < 32 and c not in "\n\t\r" for c in message
    ):
        raise ValueError("agent:invalid_text")
    if len(message.encode()) > 1500:
        raise ValueError("agent:input_too_large")
    previous = previous or {}
    if profile == "financial":
        return financial_scope(message, period, previous)
    return infrastructure_scope(message, scenario_id, previous)


def select_live_scope(profile, message, period=None, scenario_id=None, previous=None):
    """Bind explicit slots; leave interpretation and answers to LiteLLM.

    No canned answer, default/relative month or history-selected permission.
    Missing/ambiguous slots clarify before model or tool calls. The caller
    already validated, assessed and redacted text; slots still pass schemas.
    """
    if (
        BIDI_CONTROLS.search(message)
        or len(message.encode()) > 1500
        or any(ord(c) < 32 and c not in "\n\t\r" for c in message)
    ):
        raise ValueError("agent:invalid_text")
    value = normalized(message)
    if profile == "financial":
        dates, _ = periods_and_remainder(value)
        if period is not None:
            dates = sorted(set(dates + [period]))
        if len(dates) != 1 or re.search(
            r"last month|this month|الشهر الماضي|هذا الشهر", value
        ):
            return Scope(
                "clarification_required", "period_required", intent="financial"
            )
        return Scope("ready", period=dates[0], intent="financial")
    found = {
        source
        for source, topic in TOPICS.items()
        if re.search(r"(?<!\w)" + topic + r"(?!\w)", value) or value == source
    }
    if scenario_id is not None:
        found.add(scenario_id)
    if len(found) != 1 or not found.issubset(SCENARIOS):
        return Scope(
            "clarification_required", "evidence_required", intent="infrastructure"
        )
    return Scope("ready", scenario_id=found.pop(), intent="infrastructure")
