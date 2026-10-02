"""Non-sensitive mock dependencies for Phase 3 repository qualification."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .trusted_runtime import (
    ControlFailure,
    GatewayResult,
    IdentityClaims,
    PolicyDecision,
    TenantContext,
)


class Recorder:
    def __init__(self):
        self.sequence: list[str] = []
        self.litellm_calls = 0
        self.provider_calls = 0
        self.traces: list[dict[str, Any]] = []


def _mode(stage: str, mode: str) -> None:
    if mode == "timeout":
        raise TimeoutError(stage)
    if mode == "unavailable":
        raise RuntimeError(stage)


class MockAuthenticator:
    def __init__(self, recorder: Recorder, mode: str = "ok"):
        self.recorder, self.mode = recorder, mode

    def authenticate(self, authorization: str) -> IdentityClaims:
        self.recorder.sequence.append("authentication")
        _mode("authentication", self.mode)
        if authorization != "Bearer qualification-token":
            raise ControlFailure("authentication", "invalid_token")
        if self.mode == "malformed":
            return IdentityClaims("", "", frozenset())
        return IdentityClaims("qualification-subject", "tenant-qualification", frozenset({"ai:invoke"}))


class MockTenantResolver:
    def __init__(self, recorder: Recorder, mode: str = "ok"):
        self.recorder, self.mode = recorder, mode

    def resolve(self, claims: IdentityClaims) -> TenantContext:
        self.recorder.sequence.append("tenant_context")
        _mode("tenant_context", self.mode)
        if self.mode == "malformed":
            return TenantContext("", "")
        tenant_ref = hashlib.sha256(claims.tenant_claim.encode()).hexdigest()[:16]
        return TenantContext(claims.tenant_claim, tenant_ref)


class MockAuthorizer:
    def __init__(self, recorder: Recorder, mode: str = "ok"):
        self.recorder, self.mode = recorder, mode

    def authorize(self, claims: IdentityClaims, tenant: TenantContext, action: str) -> bool:
        self.recorder.sequence.append("authorization")
        _mode("authorization", self.mode)
        return self.mode != "deny" and "ai:invoke" in claims.scopes and action == "chat.complete"


class MockPolicyEngine:
    def __init__(self, recorder: Recorder, mode: str = "ok"):
        self.recorder, self.mode = recorder, mode

    def evaluate(self, request: dict[str, Any]) -> PolicyDecision | dict[str, Any]:
        self.recorder.sequence.append("agent_policy_engine")
        _mode("agent_policy_engine", self.mode)
        if self.mode == "malformed":
            return {"allowed": True}
        return PolicyDecision(self.mode != "deny", "phase3_chat_allowed" if self.mode != "deny" else "policy_denied")


class MockAnalyzer:
    def __init__(self, recorder: Recorder, mode: str = "ok"):
        self.recorder, self.mode = recorder, mode

    def analyze(self, text: str) -> Any:
        self.recorder.sequence.append("presidio_analyzer")
        _mode("presidio_analyzer", self.mode)
        if self.mode == "malformed":
            return [{"entity_type": "EMAIL_ADDRESS", "start": -1, "end": 4, "score": 1.0}]
        match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        if not match:
            return []
        return [{"entity_type": "EMAIL_ADDRESS", "start": match.start(), "end": match.end(), "score": 1.0}]


class MockAnonymizer:
    def __init__(self, recorder: Recorder, mode: str = "ok"):
        self.recorder, self.mode = recorder, mode

    def anonymize(self, text: str, analyzer_results: list[dict[str, Any]]) -> Any:
        self.recorder.sequence.append("presidio_anonymizer")
        _mode("presidio_anonymizer", self.mode)
        if self.mode == "malformed":
            return {"unexpected": "shape"}
        if self.mode == "incomplete":
            return {"text": text}
        transformed = text
        for item in reversed(analyzer_results):
            transformed = transformed[: item["start"]] + "[REDACTED]" + transformed[item["end"] :]
        return {"text": transformed}


class MockGateway:
    def __init__(self, recorder: Recorder, mode: str = "ok"):
        self.recorder, self.mode = recorder, mode

    def complete(self, model_alias: str, redacted_text: str, metadata: dict[str, str]) -> GatewayResult:
        self.recorder.sequence.append("litellm")
        self.recorder.litellm_calls += 1
        _mode("litellm", self.mode)
        self.recorder.sequence.append("provider")
        self.recorder.provider_calls += 1
        if self.mode == "malformed":
            return GatewayResult({"raw": "invalid"}, True)
        return GatewayResult(
            {"summary": "Synthetic qualification response", "classification": "informational"},
            True,
        )


class MockTraceSink:
    def __init__(self, recorder: Recorder):
        self.recorder = recorder

    def emit(self, envelope: dict[str, Any]) -> None:
        self.recorder.traces.append(envelope.copy())


def build_mock_runtime(modes: dict[str, str] | None = None):
    from .trusted_runtime import TrustedRuntime

    modes = modes or {}
    recorder = Recorder()
    runtime = TrustedRuntime(
        MockAuthenticator(recorder, modes.get("authentication", "ok")),
        MockTenantResolver(recorder, modes.get("tenant_context", "ok")),
        MockAuthorizer(recorder, modes.get("authorization", "ok")),
        MockPolicyEngine(recorder, modes.get("agent_policy_engine", "ok")),
        MockAnalyzer(recorder, modes.get("presidio_analyzer", "ok")),
        MockAnonymizer(recorder, modes.get("presidio_anonymizer", "ok")),
        MockGateway(recorder, modes.get("litellm", "ok")),
        MockTraceSink(recorder),
    )
    return runtime, recorder
