#!/usr/bin/env python3
"""One fixed local rehearsal, actual proxy/DB, explicitly simulated boundaries.

No live switch or arbitrary input selector. The existing free-text UI is separate.
A failed/started marker prevents silently recreating this operator run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.agents.audit_preparation import DurableToolAudit
from runtime.agents.composition import BoundaryBudget, compose_local
from runtime.agents.conversations import ConversationStore
from runtime.agents.gateway_budget import RunAttemptBudget
from runtime.agents.terminal_audit import TerminalAudit

CATALOG_HASH = "acc96ad5016b93345a98edf67c3cf960f92e79d0bf211f1081e59cf2dfa3523b"


def run(state):
    raw = (ROOT / "evaluation/agent-composition/synthetic-demo.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_HASH:
        raise ValueError("demo:catalog_mismatch")
    catalog = json.loads(raw)
    # O_EXCL plus fsync precedes any boundary call. Manual new runs need a new
    # stack/state; this marker is never cleared by failure handling.
    fd = os.open(state / "demo-started.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps({"scope": catalog["scope"], "catalog_sha256": CATALOG_HASH,
                                 "mode": "local_rehearsal", "live_enabled": False}) + "\n")
        stream.flush(); os.fsync(stream.fileno())
    directory = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    import psycopg
    deadline = time.monotonic() + 900
    budget = RunAttemptBudget(total=16, per_subject=8, lifetime=900)
    redaction = BoundaryBudget()
    stores, sinks = {}, []
    rows = []
    try:
        for user in ("alpha", "beta"):
            config = json.loads((state / ("application-" + user + ".json")).read_text())
            tool_path, terminal_path = state / ("rehearsal-tools-" + user), state / ("rehearsal-turns-" + user)
            tool_path.mkdir(mode=0o700); terminal_path.mkdir(mode=0o700)
            tools, terminal = DurableToolAudit(tool_path), TerminalAudit(terminal_path)
            sinks += [tools, terminal]
            agents, _, _ = compose_local(config,
                connect=lambda c=config: psycopg.connect(c["tenant_database_url"], connect_timeout=2),
                terminal_sink=terminal, tool_sink=tools, model_budget=budget, redaction_budget=redaction)
            store = ConversationStore(agents)
            stores[user] = store, store.bootstrap()[0]
        tools_used = 0
        for entry in catalog["inputs"]:
            if time.monotonic() >= deadline:
                raise ValueError("demo:deadline")
            store, session = stores[entry["user"]]
            frame = store.turn(session, {k: entry[k] for k in ("agent", "language", "question", "evidence_source")} | {"conversation_id": None})
            response = frame["response"]
            tools_used += response["tool_executions"]
            row = {"id": entry["id"], "status": response["status"],
                   "model_attempts": response["model_requests"], "tools": response["tool_executions"]}
            rows.append(row)
            if response["status"] != "completed" or tools_used > 12:
                raise ValueError("demo:terminal_failure")
        receipt = {"scope": catalog["scope"], "mode": "local_rehearsal", "live_enabled": False,
                   "cases": rows, "model_attempts": budget._used, "tools": tools_used,
                   "redaction_operations": redaction.operations, "input_output_bytes": redaction.bytes,
                   "external_model_calls": 0, "sdk_attempts": 0, "retries": 0,
                   "redaction_qualified": False, "model_quality_qualified": False}
        (state / "demo-result.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
        return receipt
    finally:
        for sink in sinks:
            sink.close()


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.state)
    except Exception:
        print("demo:blocked; no automatic retry", file=sys.stderr)
        raise SystemExit(1) from None
