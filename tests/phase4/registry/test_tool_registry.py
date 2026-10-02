import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from runtime.phase4.tool_registry import (
    RegistryFailure,
    get_tool_metadata,
    load_registry,
    resolve_tool_preconditions,
    validate_tool_metadata,
)

VALID_READ_TOOL = {
    "id": "example_get_cash_position",
    "name": "Example: Get Cash Position",
    "description": "Illustrative example only, at least forty characters of description text here.",
    "version": "0.1.0",
    "owner": "AI Infrastructure",
    "enabled": True,
    "risk_classification": "sensitive_financial_read",
    "operation_type": "read",
    "input_schema_ref": "deferred-phase-4b",
    "output_schema_ref": "deferred-phase-4b",
    "authorization": {"required_action": "example_get_cash_position.execute"},
    "approval": {"required": False, "extension_point_ref": None},
    "audit_classification": "sensitive",
    "source_system": "internal",
    "execution_boundary": {"timeout_seconds": 30, "max_calls_per_turn": 5},
}

VALID_REVERSIBLE_WRITE_TOOL = {
    **deepcopy(VALID_READ_TOOL),
    "id": "example_edit_draft_invoice",
    "operation_type": "write",
    "risk_classification": "reversible_write",
    "authorization": {"required_action": "example_edit_draft_invoice.execute"},
    "approval": {"required": True, "extension_point_ref": "phase-4c-human-approval-extension-point"},
}

VALID_IRREVERSIBLE_TOOL = {
    **deepcopy(VALID_READ_TOOL),
    "id": "example_void_invoice",
    "operation_type": "write",
    "risk_classification": "irreversible_high_impact",
    "authorization": {"required_action": "example_void_invoice.execute"},
    "approval": {"required": True, "extension_point_ref": "phase-4c-human-approval-extension-point"},
    "audit_classification": "high_sensitivity",
}


class ToolMetadataValidationTests(unittest.TestCase):
    def test_valid_read_tool_is_accepted(self):
        tool = validate_tool_metadata(VALID_READ_TOOL)
        self.assertEqual(tool.id, "example_get_cash_position")

    def test_valid_reversible_write_tool_is_accepted(self):
        tool = validate_tool_metadata(VALID_REVERSIBLE_WRITE_TOOL)
        self.assertTrue(tool.approval.required)

    def test_valid_irreversible_tool_is_accepted(self):
        tool = validate_tool_metadata(VALID_IRREVERSIBLE_TOOL)
        self.assertTrue(tool.approval.required)

    def test_malformed_metadata_missing_field_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        del body["owner"]
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_unsupported_risk_class_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["risk_classification"] = "moderate_risk"
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "unsupported_risk_class")

    def test_missing_authorization_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["authorization"] = {}
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "missing_authorization")

    def test_read_risk_with_write_operation_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["operation_type"] = "write"
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_write_risk_with_read_operation_rejected(self):
        body = deepcopy(VALID_IRREVERSIBLE_TOOL)
        body["operation_type"] = "read"
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_reversible_write_without_approval_rejected(self):
        body = deepcopy(VALID_REVERSIBLE_WRITE_TOOL)
        body["approval"] = {"required": False, "extension_point_ref": None}
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_irreversible_tool_without_approval_rejected(self):
        body = deepcopy(VALID_IRREVERSIBLE_TOOL)
        body["approval"] = {"required": False, "extension_point_ref": None}
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_source_system_outside_internal_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["source_system"] = "qoyod"
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_timeout_above_maximum_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["execution_boundary"] = {"timeout_seconds": 121, "max_calls_per_turn": 5}
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_max_calls_above_maximum_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["execution_boundary"] = {"timeout_seconds": 30, "max_calls_per_turn": 21}
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_required_action_over_length_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["authorization"] = {"required_action": "a." + "b" * 100}
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "missing_authorization")

    def test_extension_point_ref_over_length_rejected(self):
        body = deepcopy(VALID_REVERSIBLE_WRITE_TOOL)
        body["approval"] = {"required": True, "extension_point_ref": "x" * 101}
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_deferred_marker_accepted_for_both_schema_refs(self):
        body = deepcopy(VALID_READ_TOOL)
        body["input_schema_ref"] = "deferred-phase-4b"
        body["output_schema_ref"] = "deferred-phase-4b"
        tool = validate_tool_metadata(body)
        self.assertTrue(tool.has_deferred_schema)

    def test_empty_input_schema_ref_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["input_schema_ref"] = ""
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_empty_output_schema_ref_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["output_schema_ref"] = ""
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_overlength_input_schema_ref_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["input_schema_ref"] = "x" * 201
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")

    def test_overlength_output_schema_ref_rejected(self):
        body = deepcopy(VALID_READ_TOOL)
        body["output_schema_ref"] = "x" * 201
        with self.assertRaises(RegistryFailure) as ctx:
            validate_tool_metadata(body)
        self.assertEqual(ctx.exception.category, "malformed_metadata")


class RegistryLoadingFailureTests(unittest.TestCase):
    def test_malformed_json_converted_to_sanitized_failure(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{not valid json")
            path = handle.name
        try:
            with self.assertRaises(RegistryFailure) as ctx:
                load_registry(path)
            self.assertEqual(ctx.exception.category, "registry_unreadable")
        finally:
            Path(path).unlink()

    def test_missing_registry_file_converted_to_sanitized_failure(self):
        with self.assertRaises(RegistryFailure) as ctx:
            load_registry("tests/phase4/registry/does-not-exist.json")
        self.assertEqual(ctx.exception.category, "registry_unreadable")

    def test_invalid_envelope_converted_to_sanitized_failure(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"tools": []}, handle)
            path = handle.name
        try:
            with self.assertRaises(RegistryFailure) as ctx:
                load_registry(path)
            self.assertEqual(ctx.exception.category, "malformed_metadata")
        finally:
            Path(path).unlink()

    def test_duplicate_tool_id_rejected(self):
        payload = {"schema_version": 1, "tools": [VALID_READ_TOOL, deepcopy(VALID_READ_TOOL)]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        try:
            with self.assertRaises(RegistryFailure) as ctx:
                load_registry(path)
            self.assertEqual(ctx.exception.category, "malformed_metadata")
        finally:
            Path(path).unlink()


class RegistryResolutionTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry("tests/phase4/registry/sample-registry.json")

    def test_sample_registry_loads_all_three_examples(self):
        self.assertEqual(
            set(self.registry),
            {"example_get_cash_position", "example_edit_draft_invoice", "example_void_invoice"},
        )

    def test_unknown_tool_rejected(self):
        with self.assertRaises(RegistryFailure) as ctx:
            resolve_tool_preconditions(self.registry, "does_not_exist")
        self.assertEqual(ctx.exception.category, "unknown_tool")

    def test_get_tool_metadata_unknown_tool_rejected(self):
        with self.assertRaises(RegistryFailure) as ctx:
            get_tool_metadata(self.registry, "does_not_exist")
        self.assertEqual(ctx.exception.category, "unknown_tool")

    def test_disabled_tool_rejected(self):
        disabled = validate_tool_metadata({**deepcopy(VALID_READ_TOOL), "enabled": False})
        registry = {**self.registry, "example_get_cash_position": disabled}
        with self.assertRaises(RegistryFailure) as ctx:
            resolve_tool_preconditions(registry, "example_get_cash_position")
        self.assertEqual(ctx.exception.category, "disabled_tool")

    def test_write_tools_remain_blocked_by_deferred_schema_or_approval(self):
        for tool_id in ("example_edit_draft_invoice", "example_void_invoice"):
            with self.assertRaises(RegistryFailure) as ctx:
                resolve_tool_preconditions(self.registry, tool_id)
            self.assertIn(ctx.exception.category, ("schema_deferred", "approval_required_no_decision"))

    def test_read_tool_with_real_schemas_now_resolves(self):
        # As of Phase 4B, this one tool has real (non-deferred) schemas and
        # requires no approval, so it now passes the registry-resolution
        # precondition gate. This is NOT execution -- see
        # docs/phase4/phase-4b-tool-invocation-contract.md.
        resolved = resolve_tool_preconditions(self.registry, "example_get_cash_position")
        self.assertEqual(resolved.id, "example_get_cash_position")

    def test_approval_required_tool_with_real_schemas_still_blocked_without_decision(self):
        # Isolates the approval gate from the schema gate: real (non-deferred)
        # schema refs, so only "approval_required_no_decision" can fire.
        ready_but_needs_approval = validate_tool_metadata({
            **deepcopy(VALID_IRREVERSIBLE_TOOL),
            "input_schema_ref": "contracts/phase4/tools/example_void_invoice.input.schema.json",
            "output_schema_ref": "contracts/phase4/tools/example_void_invoice.output.schema.json",
        })
        registry = {"example_void_invoice": ready_but_needs_approval}
        with self.assertRaises(RegistryFailure) as ctx:
            resolve_tool_preconditions(registry, "example_void_invoice")
        self.assertEqual(ctx.exception.category, "approval_required_no_decision")

    def test_read_tool_with_real_schemas_and_no_approval_required_resolves(self):
        # Synthetic fixture proving the mechanism succeeds once Phase 4B
        # schemas exist — none of the repository's illustrative examples are
        # meant to demonstrate this today.
        ready = validate_tool_metadata({
            **deepcopy(VALID_READ_TOOL),
            "input_schema_ref": "contracts/phase4/tools/example_get_cash_position.input.schema.json",
            "output_schema_ref": "contracts/phase4/tools/example_get_cash_position.output.schema.json",
        })
        registry = {"example_get_cash_position": ready}
        resolved = resolve_tool_preconditions(registry, "example_get_cash_position")
        self.assertEqual(resolved.id, "example_get_cash_position")


if __name__ == "__main__":
    unittest.main()
