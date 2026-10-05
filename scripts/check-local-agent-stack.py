#!/usr/bin/env python3
"""Actual local proxy/key/DB/composition checks. No external provider calls."""
import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.agents.audit_preparation import DurableToolAudit
from runtime.agents.composition import compose_local
from runtime.agents.conversations import ConversationRejected, ConversationStore
from runtime.agents.terminal_audit import TerminalAudit
from runtime.phase3.trusted_runtime import ControlFailure

spec = importlib.util.spec_from_file_location("local_stack", ROOT / "scripts/local-agent-stack.py")
stack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack)


def check(state):
    import psycopg
    passed = []
    operator = json.loads((state / "operator.json").read_text())
    configs = {u: json.loads((state / ("application-" + u + ".json")).read_text()) for u in ("alpha", "beta")}
    stub_count = lambda: json.loads((state / "stub-count.json").read_text())["stub_requests"] if (state / "stub-count.json").exists() else 0
    prompt = {"agent": "financial", "message": "Expenses for 2026-01", "language": "en",
              "history": [], "period": "2026-01", "scenario_id": None, "observations": []}
    completion = {"model": "secure-financial-chat", "messages": [{"role": "user", "content": json.dumps(prompt)}], "max_tokens": 1024}
    before = stub_count()
    for key in (None, "invalid-fixture-client-key"):
        status, _ = stack.http("/chat/completions", key=key, data=completion)
        assert status in {401, 403}, "invalid client was not denied"
    key = configs["alpha"]["client_keys"]["financial"]
    assert stack.http("/key/generate", key=key, data={"models": ["secure-financial-chat"]})[0] in {401, 403}
    assert stack.http("/chat/completions", key=key, data=completion | {"model": "not-authorized-model"})[0] in {401, 403}
    assert stub_count() == before
    passed += ["missing_client_denied", "invalid_client_denied", "client_admin_route_denied", "client_unlisted_model_denied"]
    status, result = stack.http("/chat/completions", key=key, data=completion)
    assert status == 200 and result["choices"][0]["finish_reason"] == "stop"
    assert stub_count() == before + 1
    passed.append("authorized_client_reaches_actual_proxy_and_stub")
    status, issued = stack.http("/key/generate", key=operator["admin_key"], data={
        "models": ["secure-financial-chat"], "duration": "1h", "allowed_routes": ["/chat/completions"]})
    assert status == 200
    revoked = issued["key"]
    assert stack.http("/key/delete", key=operator["admin_key"], data={"keys": [revoked]})[0] == 200
    before = stub_count()
    assert stack.http("/chat/completions", key=revoked, data=completion)[0] in {401, 403}
    assert stub_count() == before
    passed.append("server_deleted_client_denied_without_upstream")
    # Read actual PostgreSQL role/policy behavior, including sequential leases.
    with psycopg.connect(configs["alpha"]["tenant_database_url"]) as db:
        role = db.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        assert role == (False, False)
        assert db.execute("SELECT COUNT(*) FROM portfolio_demo.expenses").fetchone()[0] == 0
        db.rollback()
        for tenant, total in ((stack.TENANTS["fixture-a"], 24000), (stack.TENANTS["fixture-b"], 9000)):
            db.execute("BEGIN READ ONLY")
            db.execute("SELECT pg_catalog.set_config('portfolio_demo.tenant_id',%s,true)", (tenant,))
            assert db.execute("SELECT SUM(amount_minor_units) FROM portfolio_demo.expenses WHERE period='2026-01'").fetchone()[0] == total
            db.rollback()
            assert db.execute("SELECT COUNT(*) FROM portfolio_demo.expenses").fetchone()[0] == 0
            db.rollback()
        try:
            db.execute("INSERT INTO portfolio_demo.expenses(tenant_id,period,category,amount_minor_units) VALUES(%s,'2026-01','office',1)", (stack.TENANTS["fixture-a"],))
            raise AssertionError("write allowed")
        except psycopg.Error:
            db.rollback()
    passed += ["nonowner_nobypassrls_role", "missing_tenant_returns_no_rows", "tenant_rls_sequential_lease_isolation", "readonly_write_denied"]
    for user, total in (("alpha", 24000), ("beta", 9000)):
        config = configs[user]
        tool_sink = DurableToolAudit(state / ("audit-tools-" + user))
        terminal = TerminalAudit(state / ("audit-turns-" + user))
        agents, budget, redaction = compose_local(config,
            connect=lambda: psycopg.connect(config["tenant_database_url"], connect_timeout=2),
            tool_sink=tool_sink, terminal_sink=terminal)
        store = ConversationStore(agents)
        tokens = [store.bootstrap()[0] for _ in range(2)]
        for language in ("en", "ar"):
            for profile in ("financial", "infrastructure"):
                message = ("What are my total expenses for 2026-01?" if language == "en"
                    else "ما إجمالي مصروفاتي في 2026-01؟") if profile == "financial" else (
                    "Why did Docker archive export fail?" if language == "en" else "لماذا فشل تصدير أرشيف Docker؟")
                request = {"agent": profile, "language": language, "question": message,
                           "evidence_source": "archive-export" if profile == "infrastructure" else None,
                           "conversation_id": None}
                frame = store.turn(tokens[0], request)
                assert frame["response"]["status"] == "completed", profile + ": composition blocked"
                assert frame["response"]["mode"] == "offline_simulation"
                if profile == "financial":
                    facts = {f["tool_id"]: f["result"] for f in frame["response"]["facts"]}
                    assert facts["expense_summary"]["total_minor_units"] == total
                try:
                    store.turn(tokens[1], request | {"conversation_id": frame["conversation_id"]})
                    raise AssertionError("conversation crossed session")
                except ConversationRejected:
                    pass
                store.reset(tokens[0], {"agent": profile, "conversation_id": frame["conversation_id"]})
                passed.append(user + "_" + profile + "_" + language + "_actual_composition")
        assert redaction.operations > 28 and redaction.bytes > 0
        # Reset does not replenish either shared budget.
        assert budget._used == 14
        passed.append(user + "_conversation_isolation_and_shared_accounting")
        tool_sink.close()
        terminal.close()
        reopened = TerminalAudit(state / ("audit-turns-" + user))
        assert reopened._db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 4
        reopened.close()
        passed.append(user + "_durable_terminal_reopen")
    # Actual LiteLLM envelopes for prohibited protocol forms must block dispatch.
    config = configs["alpha"]
    for mode in ("native_tool", "truncated", "cross_profile"):
        (state / "stub-control.json").write_text(json.dumps({"mode": mode}))
        tool_path, terminal_path = state / ("test-tools-" + mode), state / ("test-turns-" + mode)
        tool_path.mkdir(mode=0o700); terminal_path.mkdir(mode=0o700)
        tool_sink, terminal = DurableToolAudit(tool_path), TerminalAudit(terminal_path)
        connect = mock.Mock(side_effect=AssertionError("DB must not be reached"))
        agents, _, _ = compose_local(config, connect=connect, tool_sink=tool_sink, terminal_sink=terminal)
        core, token = agents["infrastructure"]
        result = core.run(token, {"agent": "infrastructure", "message": "Why did Docker archive export fail?",
                                  "period": None, "scenario_id": "archive-export"})
        assert result["status"] == "blocked" and result["tool_executions"] == 0
        connect.assert_not_called()
        tool_sink.close(); terminal.close()
        passed.append("actual_proxy_" + mode + "_blocks_tool_dispatch")
    (state / "stub-control.json").write_text(json.dumps({"mode": "canonical"}))
    receipt = {"mode": "actual_local_litellm_postgresql_stub", "checks_passed": passed,
               "checks": len(passed), "live_enabled": False, "external_model_calls": 0,
               "redaction_qualified": False, "model_quality_qualified": False,
               "stub_requests": stub_count(), "credentials_and_raw_responses_emitted": False}
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    try:
        check(args.state)
    except Exception as error:
        import traceback
        trace = traceback.extract_tb(error.__traceback__)
        print(json.dumps({"result": "BLOCKED", "exception_type": type(error).__name__,
            "own_frames": [{"function": f.name, "line": f.lineno} for f in trace
                           if f.filename == str(Path(__file__).resolve())]}), file=sys.stderr)
        print("local_integration:check_failed", file=sys.stderr)
        raise SystemExit(1) from None
