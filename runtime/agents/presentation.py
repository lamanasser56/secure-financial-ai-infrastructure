"""Display projections of validated facts; no authorization or model arithmetic.

The original sanitized response and canonical audit events remain intact.
Only the current fixture's SAR currency is supported (ISO 4217 scale 2).
Unknown currencies fail closed instead of silently assuming two decimals.
"""

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


def present(result):
    """Called only after the existing core has validated/minimized/redacted."""
    view = {
        "usage": {
            "simulated_model_requests": result["model_requests"],
            "external_provider_calls": sum(
                event["provider_called"] is True
                for event in result["audit"]["model_traces"]
            ),
            "tool_dispatch_attempts": result["tool_executions"],
            "token_usage": None,
            "cost": None,
            "redaction_notice": REDACTION_NOTICE,
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
                {"label": "Observed failure", "value": ci["failure"]},
                {"label": "Suspected cause", "value": ci["observation"]},
                {"label": "Proposed repair", "value": runbook["repair"]},
            ],
            supporting_evidence=[
                {"source_id": ci["source_id"], "purpose": "Synthetic CI failure"},
                {
                    "source_id": runbook["source_id"],
                    "purpose": "Approved suggestion-only runbook section",
                },
            ],
            supplemental_context={
                "source_id": image["source_id"],
                "status": image["status"],
                "high": image["high"],
                "critical": image["critical"],
                "limitations": image["limitations"],
            },
            unverified_points=[ci["unverified"], runbook["limitations"]],
        )
    else:
        summary, grouped = facts["expense_summary"], facts["expense_categories"]
        groups = grouped["categories"]
        if (
            any(
                summary[key] != grouped[key]
                for key in ("source_id", "synthetic", "period", "currency")
            )
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
                    "rank": rank,
                    "amount": format_minor_units(group["total_minor_units"], currency),
                }
                for rank, group in enumerate(groups, 1)
            ],
        }
    return view
