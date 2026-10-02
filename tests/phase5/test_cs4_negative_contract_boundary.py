from __future__ import annotations

import json
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from runtime.phase3.mocks import MockAuthenticator, MockTenantResolver, Recorder
from runtime.phase3.trusted_runtime import ControlFailure, IdentityClaims, TenantContext
from runtime.phase4.tool_invocation import (
    ALLOWED_STAGE_CATEGORIES,
    ARGUMENT_VALIDATORS,
    FALLBACK_CATEGORY,
    FALLBACK_STAGE,
    build_failure_response,
    build_validated_success_response,
    validate_example_get_cash_position_output,
    validate_invocation_envelope,
    validate_tool_invocation,
)
from runtime.phase4.tool_registry import load_registry


VALID_REQUEST = {
    "schema_version": 1,
    "request_id": "qualification-request-0001",
    "tool_id": "example_get_cash_position",
    "arguments": {"as_of_date": "2026-08-15"},
}
VALID_OUTPUT = {
    "as_of_date": "2026-08-15",
    "cash_position_minor_units": 100,
    "currency": "SAR",
}


def load_validator(path: str) -> Draft202012Validator:
    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


REQUEST_VALIDATOR = load_validator(
    "contracts/phase4/tool-invocation-request.schema.json"
)
RESPONSE_VALIDATOR = load_validator(
    "contracts/phase4/tool-invocation-response.schema.json"
)
ARGUMENT_VALIDATOR = load_validator(
    "contracts/phase4/tools/example_get_cash_position.input.schema.json"
)
OUTPUT_VALIDATOR = load_validator(
    "contracts/phase4/tools/example_get_cash_position.output.schema.json"
)


class AllowingToolAuthorizer:
    def __init__(self, recorder: Recorder) -> None:
        self.recorder = recorder

    def authorize(
        self, claims: IdentityClaims, tenant: TenantContext, action: str
    ) -> bool:
        self.recorder.sequence.append("authorization")
        return bool(claims.subject and tenant.tenant_id and action)


class ContractAssertions(unittest.TestCase):
    def assert_schema_valid(
        self, validator: Draft202012Validator, value: Any
    ) -> None:
        if not validator.is_valid(value):
            self.fail("authoritative schema rejected an expected-valid value")

    def assert_schema_invalid(
        self, validator: Draft202012Validator, value: Any
    ) -> None:
        if validator.is_valid(value):
            self.fail("authoritative schema accepted an expected-invalid value")

    def assert_envelope_rejected(self, body: Any) -> ControlFailure:
        with self.assertRaises(ControlFailure) as raised:
            validate_invocation_envelope(body)
        self.assertEqual(raised.exception.stage, "structured_input_validation")
        self.assertEqual(raised.exception.category, "invalid_request")
        return raised.exception

    def assert_not_serialized(self, prohibited: str, value: Any) -> None:
        if prohibited in json.dumps(value, sort_keys=True):
            self.fail("rejected input was echoed into a sanitized response")


class RequestContractTests(ContractAssertions):
    def test_missing_required_fields_are_rejected_by_schema_and_runtime(self):
        for field in VALID_REQUEST:
            with self.subTest(field=field):
                mutation = deepcopy(VALID_REQUEST)
                del mutation[field]
                self.assert_schema_invalid(REQUEST_VALIDATOR, mutation)
                self.assert_envelope_rejected(mutation)

    def test_wrong_field_types_and_boolean_version_are_rejected(self):
        mutations = {
            "body-array": [],
            "version-string": {**VALID_REQUEST, "schema_version": "1"},
            "version-float": {**VALID_REQUEST, "schema_version": 1.5},
            "version-boolean": {**VALID_REQUEST, "schema_version": True},
            "request-id-integer": {**VALID_REQUEST, "request_id": 1},
            "request-id-boolean": {**VALID_REQUEST, "request_id": False},
            "tool-id-integer": {**VALID_REQUEST, "tool_id": 1},
            "tool-id-boolean": {**VALID_REQUEST, "tool_id": True},
            "arguments-null": {**VALID_REQUEST, "arguments": None},
            "arguments-array": {**VALID_REQUEST, "arguments": []},
            "arguments-string": {**VALID_REQUEST, "arguments": "invalid"},
        }
        for case_id, mutation in mutations.items():
            with self.subTest(case_id=case_id):
                self.assert_schema_invalid(REQUEST_VALIDATOR, mutation)
                self.assert_envelope_rejected(mutation)

    def test_integer_valued_float_version_is_rejected_by_runtime(self):
        mutation = {**VALID_REQUEST, "schema_version": 1.0}
        self.assert_schema_valid(REQUEST_VALIDATOR, mutation)
        self.assert_envelope_rejected(mutation)

    def test_extra_envelope_field_is_rejected(self):
        mutation = {**VALID_REQUEST, "unexpected": "rejected"}
        self.assert_schema_invalid(REQUEST_VALIDATOR, mutation)
        self.assert_envelope_rejected(mutation)

    def test_identifier_minimum_and_maximum_boundaries_match_contract(self):
        valid_boundaries = (
            {**VALID_REQUEST, "request_id": "a" + "b" * 7},
            {**VALID_REQUEST, "request_id": "a" + "b" * 127},
            {**VALID_REQUEST, "tool_id": "abc"},
            {**VALID_REQUEST, "tool_id": "a" + "b" * 63},
        )
        for mutation in valid_boundaries:
            self.assert_schema_valid(REQUEST_VALIDATOR, mutation)
            request_id, tool_id, arguments = validate_invocation_envelope(mutation)
            self.assertEqual(request_id, mutation["request_id"])
            self.assertEqual(tool_id, mutation["tool_id"])
            self.assertEqual(arguments, mutation["arguments"])

    def test_invalid_identifier_boundaries_and_shapes_are_rejected(self):
        mutations = {
            "request-id-too-short": {**VALID_REQUEST, "request_id": "a" * 7},
            "request-id-too-long": {**VALID_REQUEST, "request_id": "a" * 129},
            "request-id-invalid-character": {
                **VALID_REQUEST,
                "request_id": "invalid/request",
            },
            "tool-id-too-short": {**VALID_REQUEST, "tool_id": "ab"},
            "tool-id-too-long": {**VALID_REQUEST, "tool_id": "a" * 65},
            "tool-id-uppercase": {**VALID_REQUEST, "tool_id": "Invalid_tool"},
            "tool-id-hyphen": {**VALID_REQUEST, "tool_id": "invalid-tool"},
        }
        for case_id, mutation in mutations.items():
            with self.subTest(case_id=case_id):
                self.assert_schema_invalid(REQUEST_VALIDATOR, mutation)
                self.assert_envelope_rejected(mutation)

    def test_tenant_shaped_keys_fail_closed_at_every_depth(self):
        mutations = {
            "top-level": {**VALID_REQUEST, "tenant_id": "untrusted"},
            "nested-dict": {
                **VALID_REQUEST,
                "arguments": {"context": {"tenantId": "untrusted"}},
            },
            "nested-list": {
                **VALID_REQUEST,
                "arguments": {"items": [{"TENANT_ID": "untrusted"}]},
            },
            "hyphenated": {
                **VALID_REQUEST,
                "arguments": {"tenant-id": "untrusted"},
            },
        }
        for case_id, mutation in mutations.items():
            with self.subTest(case_id=case_id):
                self.assert_envelope_rejected(mutation)

    def test_invalid_tool_ids_fail_before_end_to_end_routing(self):
        registry = load_registry("tests/phase4/registry/sample-registry.json")
        for tool_id in ("ab", "a" * 65, "invalid-tool"):
            recorder = Recorder()
            body = {**VALID_REQUEST, "tool_id": tool_id}
            with self.subTest(case_id=len(tool_id)):
                with self.assertRaises(ControlFailure) as raised:
                    validate_tool_invocation(
                        MockAuthenticator(recorder),
                        MockTenantResolver(recorder),
                        AllowingToolAuthorizer(recorder),
                        registry,
                        "Bearer qualification-token",
                        body,
                    )
                self.assertEqual(raised.exception.category, "invalid_request")
                self.assertEqual(
                    recorder.sequence,
                    ["authentication", "tenant_context"],
                )


class ToolDataContractTests(ContractAssertions):
    def test_argument_mutation_matrix_matches_authoritative_schema(self):
        validator = ARGUMENT_VALIDATORS["example_get_cash_position"]
        valid_arguments = ({}, {"as_of_date": "2026-08-15"})
        for arguments in valid_arguments:
            self.assert_schema_valid(ARGUMENT_VALIDATOR, arguments)
            self.assertEqual(validator(arguments), arguments)

        invalid_arguments = {
            "wrong-type": {"as_of_date": 20260815},
            "boolean": {"as_of_date": True},
            "bad-pattern": {"as_of_date": "15-08-2026"},
            "extra-field": {"as_of_date": "2026-08-15", "tenant_id": "x"},
        }
        for case_id, arguments in invalid_arguments.items():
            with self.subTest(case_id=case_id):
                self.assert_schema_invalid(ARGUMENT_VALIDATOR, arguments)
                with self.assertRaises(ControlFailure) as raised:
                    validator(arguments)
                self.assertEqual(raised.exception.category, "argument_schema_mismatch")

    def test_output_mutation_matrix_matches_authoritative_schema(self):
        self.assert_schema_valid(OUTPUT_VALIDATOR, VALID_OUTPUT)
        self.assertEqual(
            validate_example_get_cash_position_output(VALID_OUTPUT),
            VALID_OUTPUT,
        )
        mutations: dict[str, Any] = {
            "not-object": [],
            "date-missing": {
                key: value for key, value in VALID_OUTPUT.items() if key != "as_of_date"
            },
            "amount-missing": {
                key: value
                for key, value in VALID_OUTPUT.items()
                if key != "cash_position_minor_units"
            },
            "currency-missing": {
                key: value for key, value in VALID_OUTPUT.items() if key != "currency"
            },
            "date-wrong-type": {**VALID_OUTPUT, "as_of_date": 20260815},
            "date-bad-pattern": {**VALID_OUTPUT, "as_of_date": "15-08-2026"},
            "amount-float": {**VALID_OUTPUT, "cash_position_minor_units": 1.5},
            "amount-boolean": {**VALID_OUTPUT, "cash_position_minor_units": True},
            "amount-string": {**VALID_OUTPUT, "cash_position_minor_units": "100"},
            "currency-wrong": {**VALID_OUTPUT, "currency": "USD"},
            "extra-field": {**VALID_OUTPUT, "raw": "rejected"},
        }
        for case_id, mutation in mutations.items():
            with self.subTest(case_id=case_id):
                self.assert_schema_invalid(OUTPUT_VALIDATOR, mutation)
                with self.assertRaises(ControlFailure) as raised:
                    validate_example_get_cash_position_output(mutation)
                self.assertEqual(raised.exception.category, "output_schema_mismatch")


class ResponseContractTests(ContractAssertions):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_registry("tests/phase4/registry/sample-registry.json")
        cls.tool = cls.registry["example_get_cash_position"]

    def test_emitted_success_envelope_is_contract_valid(self):
        response = build_validated_success_response(
            VALID_REQUEST["request_id"], self.tool, VALID_OUTPUT
        )
        self.assert_schema_valid(RESPONSE_VALIDATOR, response)
        self.assertEqual(
            set(response),
            {"schema_version", "request_id", "tool_id", "status", "result"},
        )

    def test_success_builder_rejects_invalid_identifiers_and_outputs(self):
        invalid_tool = replace(self.tool, id="ab")
        cases = (
            ("a" * 7, self.tool, VALID_OUTPUT),
            ("a" * 129, self.tool, VALID_OUTPUT),
            (VALID_REQUEST["request_id"], invalid_tool, VALID_OUTPUT),
            (VALID_REQUEST["request_id"], self.tool, {"currency": "SAR"}),
        )
        for request_id, tool, output in cases:
            with self.assertRaises(ControlFailure) as raised:
                build_validated_success_response(request_id, tool, output)
            self.assertEqual(raised.exception.stage, "structured_output_validation")
            self.assertEqual(raised.exception.category, "output_schema_mismatch")

    def test_response_schema_enforces_success_failure_exclusivity(self):
        valid_success = build_validated_success_response(
            VALID_REQUEST["request_id"], self.tool, VALID_OUTPUT
        )
        valid_failure = build_failure_response(
            VALID_REQUEST["request_id"],
            VALID_REQUEST["tool_id"],
            ControlFailure("authorization", "denied"),
        )
        mutations = {
            "success-missing-result": {
                key: value
                for key, value in valid_success.items()
                if key != "result"
            },
            "success-with-error": {
                **valid_success,
                "error": {"stage": "authorization", "category": "denied"},
            },
            "failure-missing-error": {
                key: value
                for key, value in valid_failure.items()
                if key != "error"
            },
            "failure-with-result": {**valid_failure, "result": {}},
            "unknown-status": {**valid_failure, "status": "unknown"},
            "boolean-version": {**valid_failure, "schema_version": True},
            "extra-field": {**valid_failure, "raw": "rejected"},
        }
        for case_id, mutation in mutations.items():
            with self.subTest(case_id=case_id):
                self.assert_schema_invalid(RESPONSE_VALIDATOR, mutation)

    def test_every_allowed_failure_pair_emits_a_contract_valid_envelope(self):
        for stage, categories in ALLOWED_STAGE_CATEGORIES.items():
            for category in categories:
                with self.subTest(stage=stage, category=category):
                    response = build_failure_response(
                        VALID_REQUEST["request_id"],
                        VALID_REQUEST["tool_id"],
                        ControlFailure(stage, category),
                    )
                    self.assert_schema_valid(RESPONSE_VALIDATOR, response)
                    self.assertEqual(
                        response["error"],
                        {"stage": stage, "category": category},
                    )

    def test_wrong_failure_pairings_are_normalized_and_contract_valid(self):
        all_categories = set().union(*ALLOWED_STAGE_CATEGORIES.values())
        for stage, allowed in ALLOWED_STAGE_CATEGORIES.items():
            wrong_category = next(
                category for category in all_categories if category not in allowed
            )
            with self.subTest(stage=stage):
                response = build_failure_response(
                    VALID_REQUEST["request_id"],
                    VALID_REQUEST["tool_id"],
                    ControlFailure(stage, wrong_category),
                )
                self.assert_schema_valid(RESPONSE_VALIDATOR, response)
                self.assertEqual(
                    response["error"],
                    {"stage": FALLBACK_STAGE, "category": FALLBACK_CATEGORY},
                )

    def test_invalid_failure_identifiers_and_details_are_never_echoed(self):
        rejected_request_id = "rejected/request/" + "x" * 129
        rejected_tool_id = "Rejected/Tool"
        rejected_category = "rejected_sensitive_detail"
        response = build_failure_response(
            rejected_request_id,
            rejected_tool_id,
            ControlFailure("unapproved_stage", rejected_category),
        )
        self.assert_schema_valid(RESPONSE_VALIDATOR, response)
        self.assertIsNone(response["request_id"])
        self.assertIsNone(response["tool_id"])
        self.assertEqual(
            response["error"],
            {"stage": FALLBACK_STAGE, "category": FALLBACK_CATEGORY},
        )
        for rejected in (
            rejected_request_id,
            rejected_tool_id,
            rejected_category,
        ):
            self.assert_not_serialized(rejected, response)

    def test_null_failure_identifiers_emit_a_contract_valid_envelope(self):
        response = build_failure_response(
            None,
            None,
            ControlFailure("structured_input_validation", "invalid_request"),
        )
        self.assert_schema_valid(RESPONSE_VALIDATOR, response)
        self.assertIsNone(response["request_id"])
        self.assertIsNone(response["tool_id"])


if __name__ == "__main__":
    unittest.main()
