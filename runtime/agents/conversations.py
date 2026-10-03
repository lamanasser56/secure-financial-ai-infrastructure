"""Ephemeral context and quotas bound to server-resolved identity/profile.

No policy implementation lives here: every executable turn uses AgentCore,
TrustedRuntime and canonical tool governance. Sessions are simulated browser
boundaries, not production authentication. There is no disk transcript.
"""

from copy import deepcopy
from dataclasses import dataclass, field, replace
import json
import secrets
import time
import uuid

from runtime.agents.controls import DeadlineExceeded, deadline
from runtime.agents.core import Limits, TurnContext
from runtime.agents.localization import text
from runtime.agents.presentation import present, sanitized_report
from runtime.agents.schemas import validate
from runtime.phase3.trusted_runtime import (
    IdentityClaims,
    TenantContext,
    is_valid_tenant_ref,
)


class ConversationRejected(ValueError):
    """Fixed error only; never include user or provider content."""


@dataclass(frozen=True)
class ConversationLimits:
    turns: int = 8
    model_requests: int = 16
    tool_executions: int = 12
    lifetime_seconds: float = 900
    execution_seconds: float = 240
    sessions: int = 8

    def __post_init__(self):
        for name, cap in (
            ("turns", 8),
            ("model_requests", 16),
            ("tool_executions", 12),
            ("sessions", 8),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= cap:
                raise ValueError("conversation:invalid_limit")
        for name, cap in (("lifetime_seconds", 900), ("execution_seconds", 240)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not 0 < value <= cap:
                raise ValueError("conversation:invalid_limit")


@dataclass
class Conversation:
    identifier: str
    binding: tuple
    created: float
    turns: int = 0
    models: int = 0
    tools: int = 0
    seconds: float = 0
    history: tuple = ()
    previous: dict = field(default_factory=dict)


@dataclass
class Session:
    csrf: str
    created: float
    conversations: dict = field(default_factory=dict)


class ConversationStore:
    def __init__(self, agents, *, limits=None, clock=time.monotonic):
        self.agents = agents
        self.limits = limits or ConversationLimits()
        self.clock = clock
        self.sessions = {}

    def purge(self):
        now = self.clock()
        for token in tuple(self.sessions):
            if now - self.sessions[token].created >= self.limits.lifetime_seconds:
                del self.sessions[token]

    def bootstrap(self, token=None):
        self.purge()
        if token in self.sessions:
            return token, self.sessions[token]
        if len(self.sessions) >= self.limits.sessions:
            raise ConversationRejected("session_capacity")
        token = secrets.token_urlsafe(32)
        session = Session(secrets.token_urlsafe(32), self.clock())
        self.sessions[token] = session
        return token, session

    def session(self, token):
        self.purge()
        if token not in self.sessions:
            raise ConversationRejected("session_required")
        return self.sessions[token]

    def binding(self, profile):
        core, authorization = self.agents[profile]
        try:
            with deadline(2):
                claims = core.authenticator.authenticate(authorization)
                tenant = core.resolver.resolve(claims)
                if (
                    not isinstance(claims, IdentityClaims)
                    or not isinstance(tenant, TenantContext)
                    or not tenant.tenant_id
                    or not is_valid_tenant_ref(tenant.tenant_ref)
                    or core.authorizer.authorize(claims, tenant, "chat.complete")
                    is not True
                ):
                    raise ConversationRejected("conversation_access_rejected")
        except DeadlineExceeded:
            raise ConversationRejected("deadline_exceeded") from None
        return (
            claims.subject,
            claims.scopes,
            tenant.tenant_id,
            tenant.tenant_ref,
            profile,
        )

    def reset(self, token, request):
        request = validate("conversation-reset", request)
        session = self.session(token)
        profile = request["agent"]
        conversation = session.conversations.get(profile)
        if conversation is None:
            if request["conversation_id"] is not None:
                raise ConversationRejected("conversation_access_rejected")
        else:
            if (
                request["conversation_id"] not in {None, conversation.identifier}
                or self.binding(profile) != conversation.binding
            ):
                raise ConversationRejected("conversation_access_rejected")
            del session.conversations[profile]
        return {"reset": True}

    def budget(self, conversation):
        return {
            "turns": max(0, self.limits.turns - conversation.turns),
            "model_requests": max(0, self.limits.model_requests - conversation.models),
            "tool_dispatches": max(0, self.limits.tool_executions - conversation.tools),
            "execution_seconds": max(
                0, round(self.limits.execution_seconds - conversation.seconds, 3)
            ),
        }

    @staticmethod
    def retained(history, user, answer):
        result = list(history)
        for role, value in (("user", user), ("assistant", answer)):
            if value:
                preview = value.encode()[:80].decode("utf-8", errors="ignore")
                result.append({"role": role, "text": preview})
        result = result[-4:]
        while len(json.dumps(result, ensure_ascii=False).encode()) > 512:
            result.pop(0)
        return tuple(result)

    def turn(self, token, request):
        request = validate("conversation", request)
        session = self.session(token)
        profile, language = request["agent"], request["language"]
        if profile == "financial" and request["evidence_source"] is not None:
            raise ConversationRejected("invalid_request")
        started = self.clock()
        binding = self.binding(profile)
        conversation = session.conversations.get(profile)
        identifier = request["conversation_id"]
        if identifier is None:
            if conversation is not None:
                raise ConversationRejected("conversation_reset_required")
            conversation = Conversation(str(uuid.uuid4()), binding, self.clock())
            session.conversations[profile] = conversation
        elif (
            conversation is None
            or identifier != conversation.identifier
            or binding != conversation.binding
        ):
            raise ConversationRejected("conversation_access_rejected")
        core, authorization = self.agents[profile]
        remaining = self.budget(conversation)
        binding_seconds = max(0, self.clock() - started)
        remaining["execution_seconds"] = max(
            0, remaining["execution_seconds"] - binding_seconds
        )
        expired = self.clock() - conversation.created >= self.limits.lifetime_seconds
        if expired or not all(
            remaining[k] > 0
            for k in ("turns", "model_requests", "tool_dispatches", "execution_seconds")
        ):
            conversation.seconds += binding_seconds
            conversation.history, conversation.previous = (), {}
            code = "conversation_expired" if expired else "conversation_budget"
            result = {
                "request_id": str(uuid.uuid4()),
                "agent": profile,
                "status": "refused",
                "language": language,
                "mode": "offline_simulation" if core.simulation else "gateway",
                "authentication": (
                    "simulated"
                    if getattr(core.authenticator, "simulated", False)
                    else "integration_supplied"
                ),
                "tenant_ref": binding[3],
                "model_requests": 0,
                "tool_executions": 0,
                "audit": {"model_traces": [], "tool_governance": []},
                "reason_code": code,
                "question": text(code, language),
            }
        else:
            allowed = replace(
                core.limits,
                model_requests=min(
                    core.limits.model_requests, remaining["model_requests"]
                ),
                tool_executions=min(
                    core.limits.tool_executions, remaining["tool_dispatches"]
                ),
                overall_seconds=min(
                    core.limits.overall_seconds, remaining["execution_seconds"]
                ),
            )
            conversation.turns += 1
            # Reserve before dispatch. Unknown framework failures retain the
            # reservation; they cannot silently replenish a spent budget.
            conversation.models += allowed.model_requests
            conversation.tools += allowed.tool_executions
            try:
                result = core.run(
                    authorization,
                    {
                        "agent": profile,
                        "message": request["question"],
                        "period": None,
                        "scenario_id": request["evidence_source"],
                    },
                    language=language,
                    context=TurnContext(
                        deepcopy(conversation.history),
                        deepcopy(conversation.previous),
                        allowed,
                    ),
                )
                if any(
                    type(result.get(k)) is not int or not 0 <= result[k] <= cap
                    for k, cap in (
                        ("model_requests", allowed.model_requests),
                        ("tool_executions", allowed.tool_executions),
                    )
                ):
                    raise ConversationRejected("invalid_result")
                conversation.models -= allowed.model_requests - result["model_requests"]
                conversation.tools -= (
                    allowed.tool_executions - result["tool_executions"]
                )
                user = result.pop("_retained_input", None)
                previous = result.pop("_continuation", {})
                if result["status"] == "blocked":
                    conversation.history, conversation.previous = (), {}
                else:
                    conversation.previous = previous
                    conversation.history = self.retained(
                        conversation.history,
                        user,
                        result.get("answer", {}).get("summary")
                        or result.get("question"),
                    )
            except BaseException:
                conversation.history, conversation.previous = (), {}
                raise
            finally:
                conversation.seconds += max(0, self.clock() - started)
        result["presentation"] = present(result, language)
        report = sanitized_report(result)
        value = {
            "conversation_id": conversation.identifier,
            "turn_number": conversation.turns,
            "response": result,
            "report": report,
            "budget_remaining": self.budget(conversation),
        }
        if len(json.dumps(value, ensure_ascii=False).encode()) > 65536:
            raise ConversationRejected("output_too_large")
        return value
