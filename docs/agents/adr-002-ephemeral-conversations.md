# ADR: bounded ephemeral conversations and separate language views

## Status

Accepted for the authorized offline conversation/UI extension. This extends the [original demo decision](adr-001-bounded-demo-agents.md) and supersedes the English-only presentation restriction. It authorizes no live provider, credentials, cloud operation or redactor change.

## Decision

Pass actual free-text questions through the existing validated and redacted core. Use an explicit limited English/Arabic offline grammar for approved sources and financial periods; unsupported questions receive a truthful refusal. Examples only populate the question box. Clarifications retain server-owned intent/month/source slots in the same conversation.

Bind ephemeral conversations to the server-resolved subject, scopes, tenant context, pseudonymous reference, profile and browser session. Reuse TrustedRuntime, the canonical registry, invocation, policy, injection, approval, schema and audit mechanisms for every executable turn. The manager enforces quotas and context lifecycle; it is not another policy engine. Browser fields cannot select trusted identity, permissions, runtime limits, endpoint, alias or credentials.

Limit each conversation to eight turns, sixteen model request attempts, twelve tool dispatch attempts, 240 cumulative execution seconds and a non-renewing fifteen-minute session lifetime. Keep the existing four/four and sixty-second per-turn limits. Retain at most four 80-byte redacted previews within 512 serialized bytes, plus validated continuation slots. Do not persist or log transcripts. An explicit reset clears only the selected profile's context; process shutdown clears all sessions. The offline reset is not a live account-wide spend limiter.

Provide distinct Arabic RTL and English LTR views. Answers follow the selected view, independently of the input language. Technical identifiers stay unchanged and are isolated LTR within RTL prose. Switching language makes no request and never rewrites a historical message. Hide messages of the other language instead of displaying paired translations.

Export only validated fixture facts, deterministic display projections and sanitized audit events. Exclude questions, all model prose, retained context, conversation handles and credentials from downloads. A synthetic unavailable month returns availability, not invented zero expenses. The financial output contracts explicitly carry availability and receive a major tool version change; authorization remains unchanged.

## Consequences

The interface supports genuine bounded input and clarification while remaining a limited deterministic simulation. It is not general conversational intelligence or proof of live Arabic Presidio detection. Single-thread POSIX deadlines and private loopback/SSH access remain required. Idle expired context is purged on the next access or shutdown, and is unusable after its deadline. Model text and previous answers remain untrusted. Real identity, bilingual Presidio, scoped LiteLLM credentials, a qualified Gemini/Vertex route and durable minimized audit delivery remain the [single live follow-up bundle](live-follow-up-bundle.md).
