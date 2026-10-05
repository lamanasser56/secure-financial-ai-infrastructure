"""Offline denial/commit semantics; real server checks use the worker CLI."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from runtime.agents.composition import BoundaryBudget, compose_local
from runtime.agents.demo import make_demo
from runtime.agents.terminal_audit import TerminalAudit
from runtime.phase3.trusted_runtime import ControlFailure


def terminal():
    return {"schema_version": 2, "event_id": "fixture-terminal-001", "event_type": "turn_terminal",
            "occurred_at": "2026-10-05T16:00:00+00:00", "agent": "financial",
            "tenant_ref": "1" * 16, "outcome": "completed", "model_attempts": 3,
            "tool_attempts": 2, "redaction_provider": "simulated", "model_provider": "stub"}


class CompositionTests(unittest.TestCase):
    def test_locked_litellm_empty_provider_metadata_is_admitted(self):
        from runtime.agents.protocol_preparation import completion_content
        response = {"choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": "{}", "provider_specific_fields": {}}}]}
        self.assertEqual(completion_content(response), "{}")
        response["choices"][0]["message"]["provider_specific_fields"] = {"refusal": None}
        self.assertEqual(completion_content(response), "{}")
        response["choices"][0]["message"]["provider_specific_fields"] = {"injected": "content"}
        with self.assertRaises(ControlFailure):
            completion_content(response)

    def test_live_configuration_cannot_construct_local_composition(self):
        for value in ({}, {"mode": "live", "live_enabled": True},
                      {"mode": "local_stub", "live_enabled": True}):
            with self.assertRaises(ValueError):
                compose_local(value, connect=mock.Mock(), terminal_sink=mock.Mock(), tool_sink=mock.Mock())

    def test_shared_operations_are_not_reset_by_profile_or_conversation(self):
        budget = BoundaryBudget(operations=2)
        budget.reserve("English")
        budget.reserve("العربية")
        with self.assertRaises(ControlFailure):
            budget.reserve("next profile")
        self.assertEqual(budget.operations, 2)

    def test_utf8_byte_budget_and_deadline_are_independent(self):
        now = [1]
        budget = BoundaryBudget(byte_limit=6, lifetime=1, clock=lambda: now[0])
        budget.reserve("ععع")
        with self.assertRaises(ControlFailure):
            budget.reserve("a")
        now[0] = 2
        with self.assertRaises(ControlFailure):
            budget.reserve("x")
        for value in (None, "a" * 4097, "\ud800"):
            with self.assertRaises(ControlFailure):
                BoundaryBudget().reserve(value)

    def test_output_bytes_share_the_input_ledger(self):
        budget = BoundaryBudget(byte_limit=7)
        budget.reserve("abc")
        budget.accept_output("عع")
        self.assertEqual((budget.operations, budget.bytes), (1, 7))
        with self.assertRaises(ControlFailure):
            budget.reserve("x")

    def test_duplicate_transport_fields_are_rejected(self):
        from runtime.phase3.adapters import _unique_response
        with self.assertRaises(ValueError):
            json.loads('{"choices":[],"choices":[{}]}', object_pairs_hook=_unique_response)

    def test_durable_admission_failure_prevents_tool_dispatch(self):
        core, authorization = make_demo("financial")
        core.audit_sink = mock.Mock()
        core.audit_sink.append.side_effect = ControlFailure("audit", "invalid_event")
        with mock.patch.object(core.tools, "execute", wraps=core.tools.execute) as handler:
            result = core.run(authorization, {"agent": "financial", "message": "Expenses for 2026-01",
                                              "period": None, "scenario_id": None})
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["tool_executions"], 0)
            handler.assert_not_called()

    def test_authentication_denial_precedes_redactor_gateway_and_tools(self):
        core, _ = make_demo("financial")
        with mock.patch.object(core.redactor, "redact") as redactor, \
                mock.patch.object(core.gateway, "complete") as gateway, \
                mock.patch.object(core.tools, "execute") as handler:
            result = core.run("Bearer forged", {"agent": "financial", "message": "Expenses for 2026-01",
                                                 "period": None, "scenario_id": None})
            self.assertEqual(result["status"], "blocked")
            for boundary in (redactor, gateway, handler):
                boundary.assert_not_called()

    def test_existing_rehearsal_marker_blocks_before_composition(self):
        import importlib.util
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location("rehearsal", root / "scripts/rehearse-integrated-demo.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as state:
            Path(state, "demo-started.json").write_text("{}")
            with mock.patch.object(module, "compose_local") as factory:
                with self.assertRaises(FileExistsError):
                    module.run(Path(state))
                factory.assert_not_called()


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        os.chmod(self.directory.name, 0o700)

    def tearDown(self):
        self.directory.cleanup()

    def test_commit_reopen_and_duplicate_denial_without_replay(self):
        journal = TerminalAudit(self.directory.name)
        journal.append(terminal())
        journal.close()
        journal = TerminalAudit(self.directory.name)
        with self.assertRaises(ControlFailure):
            journal.append(terminal())
        self.assertEqual(journal._db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
        journal.close()

    def test_transcript_credential_and_provider_authority_fields_rejected(self):
        journal = TerminalAudit(self.directory.name)
        for key in ("prompt", "arguments", "response", "credential", "exception"):
            with self.subTest(key=key), self.assertRaises(ControlFailure):
                journal.append(terminal() | {key: "private text"})
        for key, value in (("model_provider", "vertex"), ("redaction_provider", "google_sdp"),
                           ("model_attempts", True), ("occurred_at", "invalid")):
            with self.subTest(key=key), self.assertRaises(ControlFailure):
                journal.append(terminal() | {key: value})
        journal.close()

    def test_capacity_and_commit_failures_block(self):
        journal = TerminalAudit(self.directory.name, maximum=1)
        journal.append(terminal())
        with self.assertRaises(ControlFailure):
            journal.append(terminal() | {"event_id": "fixture-terminal-002"})
        journal.close()
        journal = TerminalAudit(self.directory.name)
        journal._db.close()
        with self.assertRaises(ControlFailure):
            journal.append(terminal() | {"event_id": "fixture-terminal-003"})

    def test_corrupt_or_wrong_version_history_blocks_reopen(self):
        journal = TerminalAudit(self.directory.name)
        journal.append(terminal())
        journal._db.execute("UPDATE events SET event=?", (json.dumps(terminal() | {"schema_version": 1}),))
        journal._db.commit()
        journal.close()
        with self.assertRaises(ControlFailure):
            TerminalAudit(self.directory.name)

    def test_unsafe_existing_file_cannot_be_repaired_blindly(self):
        path = Path(self.directory.name) / "tool-audit.sqlite"
        path.write_bytes(b"")
        path.chmod(0o644)
        with self.assertRaises(ControlFailure):
            TerminalAudit(self.directory.name)
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)
