"""Explicit offline test doubles and future trusted gateway construction."""

import json
import os
import re

from runtime.agents.controls import DemoIdentity, PROFILES
from runtime.agents.core import AgentCore
from runtime.agents.schemas import ROOT
from runtime.agents.localization import fixture_text, text
from runtime.phase3.adapters import (
    CLIENT_KEY_ENV_VAR,
    HttpLiteLLMGateway,
    HttpPresidioAnalyzer,
    HttpPresidioAnonymizer,
    PresidioRedactor,
)
from runtime.phase3.trusted_runtime import GatewayResult
from runtime.phase4.tool_registry import load_registry


class SyntheticAnalyzer:
    """Test-double recognition; NOT real Presidio detection evidence."""

    offline_simulation = True

    def analyze(self, text):
        return [
            {
                "entity_type": "EMAIL_ADDRESS",
                "start": m.start(),
                "end": m.end(),
                "score": 1.0,
            }
            for m in re.finditer(
                r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text
            )
        ]


class SyntheticAnonymizer:
    offline_simulation = True

    def anonymize(self, text, analyzer_results):
        for item in reversed(analyzer_results):
            text = text[: item["start"]] + "[REDACTED]" + text[item["end"] :]
        return {"text": text}


class FakeGateway:
    """Deterministic simulation at the GatewayClient seam; no HTTP/provider."""

    offline_simulation = True

    def complete(self, model_alias, redacted_text, metadata):
        p = json.loads(redacted_text)
        language = p.get("language", "en")
        obs = p["observations"]
        seen = {o["tool_id"] for o in obs}
        sequence = (
            ["read_ci_summary", "read_image_summary", "read_runbook_section"]
            if p["agent"] == "infrastructure"
            else ["expense_summary", "expense_categories"]
        )
        next_tool = next((t for t in sequence if t not in seen), None)
        if next_tool:
            args = (
                {"scenario_id": p["scenario_id"]}
                if next_tool == "read_ci_summary"
                else (
                    {"section_id": p["scenario_id"]}
                    if next_tool == "read_runbook_section"
                    else (
                        {"period": p["period"]}
                        if next_tool.startswith("expense_")
                        else {}
                    )
                )
            )
            decision = {"kind": "tool", "tool_id": next_tool, "arguments": args}
        else:
            facts = {o["tool_id"]: o["result"] for o in obs}
            decision = {
                "kind": "final",
                "agent": p["agent"],
                "language": language,
                "period": p["period"] if p["agent"] == "financial" else None,
                "evidence_ids": list(
                    dict.fromkeys(
                        o["result"]["source_id"]
                        for o in obs
                        if o["tool_id"] != "read_image_summary"
                    )
                ),
                "limitations": text("simulationLimit", language),
            }
            if p["agent"] == "infrastructure":
                ci, runbook = facts["read_ci_summary"], facts["read_runbook_section"]
                decision.update(
                    summary=text("infraSummary", language),
                    observed_failure=fixture_text(ci["failure"], language),
                    suspected_cause=fixture_text(ci["observation"], language),
                    proposed_repair=fixture_text(runbook["repair"], language),
                )
            else:
                summary = facts["expense_summary"]
                categories = facts["expense_categories"]["categories"]
                highest = categories[0]["category"]
                decision["summary"] = text(
                    "financeSummary",
                    language,
                    period=summary["period"],
                    count=summary["expense_count"],
                    category=text(highest, language),
                )
        return GatewayResult(
            {
                "summary": json.dumps(
                    decision, ensure_ascii=False, separators=(",", ":")
                ),
                "classification": "informational",
            },
            False,
            "offline_simulation",
        )


def make_demo(
    profile,
    user="demo-alpha",
    *,
    key=None,
    gateway=None,
    redactor=None,
    tools=None,
    limits=None,
):
    registry = load_registry(ROOT / "contracts/agents/tool-registry.json")
    identity = DemoIdentity(
        user,
        {registry[t].authorization.required_action for t in PROFILES[profile]},
        key=key,
    )
    core = AgentCore(
        profile,
        identity,
        identity,
        identity,
        (
            redactor
            if redactor is not None
            else PresidioRedactor(SyntheticAnalyzer(), SyntheticAnonymizer())
        ),
        gateway if gateway is not None else FakeGateway(),
        simulation=True,
        tools=tools,
        limits=limits,
    )
    return core, identity.startup_authorization()


def prepare_gateway_core(
    profile,
    authenticator,
    resolver,
    authorizer,
    *,
    base_url,
    analyzer_url,
    anonymizer_url,
):
    """Integration factory only. Entry points never call it under this scope.

    Provider identity belongs to LiteLLM. The client key must be a separately
    scoped virtual key, not the gateway's administrative/master credential.
    URLs/alias/client credentials are startup-selected, never request fields.
    """
    key = os.environ.get(CLIENT_KEY_ENV_VAR)
    master = os.environ.get("PORTFOLIO_LITELLM_MASTER_KEY")
    if not key or key == master or getattr(authenticator, "simulated", False):
        raise ValueError("agent:invalid_live_integration")
    redactor = PresidioRedactor(
        HttpPresidioAnalyzer(analyzer_url, timeout=4),
        HttpPresidioAnonymizer(anonymizer_url, timeout=4),
    )
    return AgentCore(
        profile,
        authenticator,
        resolver,
        authorizer,
        redactor,
        HttpLiteLLMGateway(base_url, timeout=8),
        simulation=False,
    )
