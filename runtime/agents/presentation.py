"""Display projections of validated facts; no authorization or model arithmetic.

The original sanitized response and canonical audit events remain intact.
Only the current fixture's SAR currency is supported (ISO 4217 scale 2).
Unknown currencies fail closed instead of silently assuming two decimals.
"""

from copy import deepcopy
from runtime.agents.localization import fixture_text, text
from runtime.agents.terminal_diagnostics import validate_terminal_failure

CURRENCY_SCALES = {"SAR": 2}
REDACTION_NOTICE = (
    "Simulated redaction completion using synthetic service doubles. "
    "Live Presidio detection is unproven; Presidio remains authoritative."
)


def format_minor_units(value, currency):
    if type(value) is not int or value < 0 or currency not in CURRENCY_SCALES:
        raise ValueError("ui:unsupported_amount")
    scale = CURRENCY_SCALES[currency]
    whole, fraction = divmod(value, 10**scale)
    return f"{currency} {whole}.{fraction:0{scale}d}"


def present(result, language=None):
    """Called only after the existing core has validated/minimized/redacted."""
    language = language or result.get("language", "en")
    simulated = result["mode"] == "offline_simulation"
    measurement = result.get("local_transport", result.get("gateway_measurement", {}))
    view = {
        "usage": {
            "simulated_model_requests": (
                measurement.get('http_attempts', result['model_requests']) if simulated else 0),
            'model_invocation_attempts': result['model_requests'],
            "gateway_http_attempts": measurement.get("http_attempts"),
            "external_provider_calls": (
                0 if simulated else measurement.get("provider_receipts")
            ),
            "tool_dispatch_attempts": result["tool_executions"],
            "token_usage": measurement.get("usage_tokens") if not simulated else None,
            "cost": None,
            "redaction_notice": text(
                "redaction" if simulated else "realRedactionRequired", language
            ),
        }
    }
    if result["status"] != "completed":
        return view
    facts = {fact["tool_id"]: fact["result"] for fact in result["facts"]}
    if result["agent"] == "infrastructure":
        ci, runbook, image = (
            facts["read_ci_summary"],
            facts["read_runbook_section"],
            facts["read_image_summary"],
        )
        view.update(
            diagnosis=[
                {
                    "label": text("observedFailure", language),
                    "value": fixture_text(ci["failure"], language),
                },
                {
                    "label": text("suspectedCause", language),
                    "value": fixture_text(ci["observation"], language),
                },
                {
                    "label": text("proposedRepair", language),
                    "value": fixture_text(runbook["repair"], language),
                },
            ],
            supporting_evidence=[
                {"source_id": ci["source_id"], "purpose": text("ciPurpose", language)},
                {
                    "source_id": runbook["source_id"],
                    "purpose": text("runbookPurpose", language),
                },
            ],
            supplemental_context={
                "source_id": image["source_id"],
                "status": image["status"],
                "status_label": text("fixtureQualified", language),
                "high": image["high"],
                "critical": image["critical"],
                "limitations": fixture_text(image["limitations"], language),
            },
            unverified_points=[
                fixture_text(ci["unverified"], language),
                fixture_text(runbook["limitations"], language),
            ],
        )
    else:
        summary, grouped = facts["expense_summary"], facts["expense_categories"]
        groups = grouped["categories"]
        if (
            any(
                summary[key] != grouped[key]
                for key in (
                    "source_id",
                    "synthetic",
                    "period",
                    "currency",
                    "data_available",
                )
            )
            or summary["data_available"] is not True
            or sum(g["total_minor_units"] for g in groups)
            != summary["total_minor_units"]
            or sum(g["expense_count"] for g in groups) != summary["expense_count"]
            or groups
            != sorted(groups, key=lambda g: (-g["total_minor_units"], g["category"]))
        ):
            raise ValueError("ui:inconsistent_tool_facts")
        currency = summary["currency"]
        view["financial"] = {
            **summary,
            "currency_scale": CURRENCY_SCALES[currency],
            "total": format_minor_units(summary["total_minor_units"], currency),
            "categories": [
                {
                    **group,
                    "category_label": text(group["category"], language),
                    "rank": rank,
                    "amount": format_minor_units(group["total_minor_units"], currency),
                }
                for rank, group in enumerate(groups, 1)
            ],
        }
    return view


def sanitized_report(result):
    """No question, model answer, history, session token or conversation handle.

    Only closed audit events, validated fixture facts and their deterministic
    presentation enter downloads. Even redacted model prose is not exported.
    """
    fields = (
        "request_id",
        "agent",
        "status",
        "mode",
        "authentication",
        "language",
        "tenant_ref",
        "model_requests",
        "tool_executions",
        "audit",
        "gateway_measurement",
        "facts",
        "availability",
        "presentation",
        "limitations",
        "reason_code",
        'local_transport',
        'model_attempt_accounting',
        'terminal_failure',
    )
    if result['status'] == 'blocked':
        validate_terminal_failure(result['terminal_failure'])
    return {
        "schema_version": 2,
        **deepcopy({key: result[key] for key in fields if key in result}),
    }
