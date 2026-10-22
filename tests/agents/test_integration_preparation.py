"""Offline response/transaction/audit contracts; no provider or deployed DB."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from runtime.agents.audit_preparation import DurableToolAudit
from runtime.agents.protocol_preparation import canonical_decision, completion_content
from runtime.phase3.trusted_runtime import ControlFailure, IdentityClaims, TenantContext


def envelope(decision):
    return json.dumps({"summary": json.dumps(decision, ensure_ascii=False),
                       "classification": "informational"}, ensure_ascii=False)


def response(content):
    return {"choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}]}


class ProtocolTests(unittest.TestCase):
    def test_bilingual_complete_proposals_reuse_registry_without_dispatch(self):
        for summary in ("Expenses", "المصروفات", "Expenses المصروفات"):
            value = {"kind": "final", "agent": "financial", "summary": summary,
                     "limitations": "Fixture only", "period": "2026-01",
                     "evidence_ids": ["fixture-summary"]}
            # Non-sensitive text does not select tools; canonical schemas decide.
            content = envelope(value)
            self.assertEqual(completion_content(response(content)), content)
            self.assertEqual(canonical_decision(content), value)
        tool = {"kind": "tool", "tool_id": "expense_summary", "arguments": {"period": "2026-01"}}
        self.assertEqual(canonical_decision(envelope(tool)), tool)

    def test_locked_litellm_optional_null_fields_are_not_tool_calls(self):
        value = response(envelope({"kind": "clarification", "reason_code": "period_required"}))
        value["choices"][0]["message"].update(tool_calls=None, function_call=None, refusal=None)
        self.assertIn("summary", completion_content(value))
        value["choices"][0]["index"] = False
        with self.assertRaises(ControlFailure): completion_content(value)

    def test_parallel_native_legacy_mixed_refusal_and_truncation_denied(self):
        for field, value in (("tool_calls", [{"type": "function"}]),
                             ("function_call", {"name": "expense_summary"}),
                             ("refusal", "sensitive provider message")):
            result = response("valid-looking content")
            result["choices"][0]["message"][field] = value
            with self.subTest(field=field), self.assertRaises(ControlFailure) as caught:
                completion_content(result)
            self.assertNotIn("sensitive", str(caught.exception))
        for finish in ("length", "tool_calls", "content_filter", None):
            result = response("{}"); result["choices"][0]["finish_reason"] = finish
            with self.subTest(finish=finish), self.assertRaises(ControlFailure):
                completion_content(result)

    def test_ambiguous_chunks_roles_and_utf8_bounds_denied(self):
        for result in ({}, {"choices": []}, {"choices": response("x")["choices"] * 2},
                       {"choices": [{"index": 0, "finish_reason": "stop", "delta": {"content": "x"}}]}):
            with self.assertRaises(ControlFailure): completion_content(result)
        for content in (None, [], "ع" * 2049, "\ud800"):
            with self.assertRaises(ControlFailure): completion_content(response(content))
        result = response("{}"); result["choices"][0]["message"]["role"] = "tool"
        with self.assertRaises(ControlFailure): completion_content(result)

    def test_duplicate_wrapper_decision_and_argument_keys_denied(self):
        values = ('{"summary":"{}","summary":"{}","classification":"informational"}',
                  json.dumps({"summary": '{"kind":"refusal","kind":"tool","reason_code":"out_of_scope"}',
                              "classification": "informational"}),
                  json.dumps({"summary": '{"kind":"tool","tool_id":"expense_summary","arguments":{"period":"2026-01","period":"2026-02"}}',
                              "classification": "informational"}))
        for value in values:
            with self.assertRaises(ControlFailure): canonical_decision(value)

    def test_unregistered_tool_injected_tenant_and_invalid_month_denied(self):
        for tool, arguments in (("shell", {}), ("expense_summary", {"period": "2026-13"}),
                                ("expense_summary", {"period": "2026-01", "tenant_id": "another"}),
                                ("expense_summary", {"period": "٢٠٢٦-٠١"})):
            with self.assertRaises(ControlFailure):
                canonical_decision(envelope({"kind": "tool", "tool_id": tool, "arguments": arguments}))


class DurableAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.event = json.loads(Path("tests/phase4/governance/sample-governance-fixtures.json").read_text())["audit_event"]

    def test_committed_event_survives_close_and_fresh_process(self):
        import subprocess, sys
        journal = DurableToolAudit(self.path); journal.append(self.event); journal.close()
        script = "from runtime.agents.audit_preparation import DurableToolAudit; import sys; j=DurableToolAudit(sys.argv[1]); j.close()"
        subprocess.run([sys.executable, "-B", "-c", script, str(self.path)], check=True, capture_output=True)
        self.assertEqual((self.path / "tool-audit.sqlite").stat().st_mode & 0o777, 0o600)
        db = sqlite3.connect(self.path / "tool-audit.sqlite")
        self.assertEqual(json.loads(db.execute("SELECT event FROM events").fetchone()[0]), self.event)
        db.close()

    def test_raw_extra_fields_rejected_without_persistence(self):
        journal = DurableToolAudit(self.path); self.addCleanup(journal.close)
        for key in ("prompt", "arguments", "result", "exception", "credential", "provider_response"):
            with self.assertRaises(ControlFailure): journal.append({**self.event, key: "private"})
        self.assertEqual(journal._db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)

    def test_duplicate_ids_full_capacity_and_closed_sink_block(self):
        journal = DurableToolAudit(self.path, maximum=1)
        journal.append(self.event)
        with self.assertRaises(ControlFailure): journal.append(self.event)
        with self.assertRaises(ControlFailure): journal.append({**self.event, "event_id": "different-event-id"})
        journal.close()
        with self.assertRaises(ControlFailure): journal.append(self.event)

    def test_corrupt_or_sensitive_history_rejected_on_reopen(self):
        journal = DurableToolAudit(self.path); journal.append(self.event); journal.close()
        db = sqlite3.connect(self.path / "tool-audit.sqlite")
        db.execute("UPDATE events SET event=?", (json.dumps({**self.event, "prompt": "private"}),))
        db.commit(); db.close()
        with self.assertRaises(ControlFailure): DurableToolAudit(self.path)

    def test_link_writable_mode_and_unexpected_file_rejected(self):
        target = self.path / "tool-audit.sqlite"
        target.symlink_to(self.path / "missing")
        with self.assertRaises(ControlFailure): DurableToolAudit(self.path)
        target.unlink()
        journal = DurableToolAudit(self.path); journal.close()
        target.chmod(0o660)
        with self.assertRaises(ControlFailure): DurableToolAudit(self.path)
        target.chmod(0o600)
        os.link(target, self.path / "alias")
        with self.assertRaises(ControlFailure): DurableToolAudit(self.path)

    def test_failed_commit_prevents_proposed_dispatch_and_emits_no_db_details(self):
        journal = DurableToolAudit(self.path); self.addCleanup(journal.close)
        real = journal._db
        fake = mock.Mock(wraps=real)
        fake.commit.side_effect = OSError("private filesystem details")
        journal._db = fake
        dispatch = mock.Mock()
        with self.assertRaises(ControlFailure) as caught:
            journal.append(self.event)
            dispatch()
        self.assertNotIn("private", str(caught.exception))
        dispatch.assert_not_called()
        self.assertEqual(real.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
