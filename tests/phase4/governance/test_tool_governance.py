import inspect
import unittest
from datetime import datetime, timezone

import runtime.phase4 as phase4
from runtime.phase3.trusted_runtime import ControlFailure
from runtime.phase4.tool_governance import (
    GovernedToolInvocation, validate_and_govern_tool_invocation,
)
from runtime.phase4.tool_invocation import (
    PendingGovernanceToolInvocation,
    _validate_tool_invocation_pending_governance,
    build_validated_success_response,
    validate_tool_invocation,
)
from runtime.phase4.tool_policy import PolicyOutcome, ToolPolicyDecision
from runtime.phase4.tool_registry import (
    RegistryFailure, RegistryReadyToolPendingGovernance,
    _resolve_registry_readiness_for_governance, load_registry,
    resolve_tool_preconditions,
)
from _mocks import (
    ALLOW_DECISION, ENGINE_APPROVAL_DECISION, REGISTRY_APPROVAL_DECISION,
    GovernanceRecorder, MockApprovalVerifier, MockPromptInjectionAssessor,
    MockToolPolicyEngine, VALID_REQUEST, build_identity_dependencies,
    load_fixtures, registry_requiring_approval,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


class GovernanceCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry(
            "tests/phase4/registry/sample-registry.json"
        )
        fixtures = load_fixtures()
        self.server_decision = fixtures["approval_decision"]
        self.registry_decision = fixtures["registry_approval_decision"]

    def test_allow_read_returns_only_governed_state(self):
        result, recorder, policy, verifier = self._run()
        self.assertIsInstance(result, GovernedToolInvocation)
        self.assertNotIsInstance(result, PendingGovernanceToolInvocation)
        self.assertEqual(result.policy_outcome, PolicyOutcome.ALLOW)
        self.assertEqual(policy.calls, 1)
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(
            recorder.sequence,
            ["authentication", "tenant_context", "authorization",
             "prompt_injection_assessment", "agent_policy_engine"],
        )

    def test_policy_deny_blocks(self):
        with self.assertRaises(ControlFailure) as ctx:
            self._run(policy_decision=ToolPolicyDecision(
                PolicyOutcome.DENY, "engine_denied"
            ))
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("agent_policy_engine", "denied"),
        )

    def test_registry_required_tool_policy_allow_is_malformed(self):
        recorder = GovernanceRecorder()
        policy = MockToolPolicyEngine(recorder, ALLOW_DECISION)
        verifier = MockApprovalVerifier(recorder, self.registry_decision)
        with self.assertRaises(ControlFailure) as ctx:
            self._run_dependencies(
                recorder, policy, verifier,
                registry=registry_requiring_approval(),
                approval_id="approval-qualification-0002",
            )
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("agent_policy_engine", "malformed_decision"),
        )
        self.assertEqual(policy.calls, 1)
        self.assertEqual(verifier.calls, 0)

    def test_registry_explicit_reason_calls_verifier_once(self):
        result, _, _, verifier = self._run(
            registry=registry_requiring_approval(),
            policy_decision=REGISTRY_APPROVAL_DECISION,
            server_decision=self.registry_decision,
            approval_id="approval-qualification-0002",
        )
        self.assertIsInstance(result, GovernedToolInvocation)
        self.assertEqual(verifier.calls, 1)

    def test_missing_approval_id_does_not_call_verifier(self):
        recorder = GovernanceRecorder()
        policy = MockToolPolicyEngine(recorder, ENGINE_APPROVAL_DECISION)
        verifier = MockApprovalVerifier(recorder, self.server_decision)
        with self.assertRaises(ControlFailure) as ctx:
            self._run_dependencies(recorder, policy, verifier, approval_id=None)
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("human_approval_verification", "missing_decision"),
        )
        self.assertEqual(verifier.calls, 0)

    def test_valid_approval_id_calls_verifier_exactly_once(self):
        result, _, _, verifier = self._run(
            policy_decision=ENGINE_APPROVAL_DECISION,
            approval_id="approval-qualification-0001",
        )
        self.assertIsInstance(result, GovernedToolInvocation)
        self.assertEqual(verifier.calls, 1)

    def test_suspected_injection_calls_neither_policy_nor_verifier(self):
        recorder = GovernanceRecorder()
        assessor = MockPromptInjectionAssessor(recorder, "suspected")
        policy = MockToolPolicyEngine(recorder, ENGINE_APPROVAL_DECISION)
        verifier = MockApprovalVerifier(recorder, self.server_decision)
        with self.assertRaises(ControlFailure) as ctx:
            self._run_dependencies(
                recorder, policy, verifier, assessor=assessor,
                approval_id="approval-qualification-0001",
            )
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("prompt_injection_assessment", "suspected_injection"),
        )
        self.assertEqual(policy.calls, 0)
        self.assertEqual(verifier.calls, 0)

    def test_policy_raw_exception_is_closed(self):
        recorder = GovernanceRecorder()
        policy = MockToolPolicyEngine(
            recorder, ALLOW_DECISION, mode="unavailable"
        )
        verifier = MockApprovalVerifier(recorder, self.server_decision)
        with self.assertRaises(ControlFailure) as ctx:
            self._run_dependencies(recorder, policy, verifier)
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("agent_policy_engine", "unavailable"),
        )
        self.assertNotIn("sensitive-detail", str(ctx.exception))

    def test_approval_raw_exception_is_closed(self):
        recorder = GovernanceRecorder()
        policy = MockToolPolicyEngine(recorder, ENGINE_APPROVAL_DECISION)
        verifier = MockApprovalVerifier(
            recorder, self.server_decision, mode="unavailable"
        )
        with self.assertRaises(ControlFailure) as ctx:
            self._run_dependencies(
                recorder, policy, verifier,
                approval_id="approval-qualification-0001",
            )
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("human_approval_verification", "unavailable"),
        )
        self.assertNotIn("sensitive-detail", str(ctx.exception))

    def test_coordinator_accepts_id_not_decision(self):
        params = inspect.signature(validate_and_govern_tool_invocation).parameters
        self.assertIn("approval_id", params)
        self.assertNotIn("approval_decision", params)

    def test_no_mode_boolean_or_executor_bypass(self):
        params = inspect.signature(validate_and_govern_tool_invocation).parameters
        for forbidden in (
            "approval_decision_supported", "skip_approval", "governance_mode",
            "allow_pending", "executor", "gateway", "litellm", "provider",
        ):
            self.assertNotIn(forbidden, params)

    def _run(
        self, *, registry=None, policy_decision=ALLOW_DECISION,
        server_decision=None, approval_id=None,
    ):
        recorder = GovernanceRecorder()
        policy = MockToolPolicyEngine(recorder, policy_decision)
        verifier = MockApprovalVerifier(
            recorder, server_decision or self.server_decision
        )
        result = self._run_dependencies(
            recorder, policy, verifier, registry=registry, approval_id=approval_id
        )
        return result, recorder, policy, verifier

    def _run_dependencies(
        self, recorder, policy, verifier, *, registry=None, assessor=None,
        approval_id=None,
    ):
        authenticator, tenant_resolver, authorizer = build_identity_dependencies(
            recorder
        )
        return validate_and_govern_tool_invocation(
            authenticator, tenant_resolver, authorizer,
            assessor or MockPromptInjectionAssessor(recorder, "clear"),
            policy, verifier, registry or self.registry,
            "Bearer qualification-token", VALID_REQUEST, approval_id, now=NOW,
        )


class InternalCompositionTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry(
            "tests/phase4/registry/sample-registry.json"
        )

    def test_internal_registry_result_is_pending(self):
        result = _resolve_registry_readiness_for_governance(
            registry_requiring_approval(), "example_get_cash_position"
        )
        self.assertIsInstance(result, RegistryReadyToolPendingGovernance)

    def test_public_resolver_retains_approval_floor(self):
        with self.assertRaises(RegistryFailure) as ctx:
            resolve_tool_preconditions(
                registry_requiring_approval(), "example_get_cash_position"
            )
        self.assertEqual(ctx.exception.category, "approval_required_no_decision")

    def test_public_phase4b_invocation_retains_floor(self):
        recorder = GovernanceRecorder()
        dependencies = build_identity_dependencies(recorder)
        with self.assertRaises(ControlFailure) as ctx:
            validate_tool_invocation(
                *dependencies, registry_requiring_approval(),
                "Bearer qualification-token", VALID_REQUEST,
            )
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("structured_input_validation", "approval_required_no_decision"),
        )

    def test_private_invocation_result_is_pending(self):
        recorder = GovernanceRecorder()
        result = _validate_tool_invocation_pending_governance(
            *build_identity_dependencies(recorder), registry_requiring_approval(),
            "Bearer qualification-token", VALID_REQUEST,
        )
        self.assertIsInstance(result, PendingGovernanceToolInvocation)
        self.assertNotIsInstance(result, GovernedToolInvocation)

    def test_pending_types_not_exported(self):
        self.assertFalse(hasattr(phase4, "PendingGovernanceToolInvocation"))
        self.assertFalse(hasattr(phase4, "RegistryReadyToolPendingGovernance"))

    def test_pending_registry_wrapper_rejected_by_success_builder(self):
        pending = _resolve_registry_readiness_for_governance(
            self.registry, "example_get_cash_position"
        )
        with self.assertRaises(ControlFailure) as ctx:
            build_validated_success_response(
                "qualification-request-0001", pending,
                {"as_of_date": "2026-08-01", "cash_position_minor_units": 100,
                 "currency": "SAR"},
            )
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("structured_output_validation", "output_schema_mismatch"),
        )


if __name__ == "__main__":
    unittest.main()
