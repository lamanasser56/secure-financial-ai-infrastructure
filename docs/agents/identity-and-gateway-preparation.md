# Independent identity and gateway preparation

2026-10-04: reversible candidates only; no live UI selection, cloud identity,
provider request, publication or credential issuance. Uses existing `Authenticator`,
`TenantResolver`, `Authorizer`, `GatewayClient`, `TrustedRuntime`, registry and
invocation controls; no parallel policy engine or login service.

## Trusted identity candidate

[JWT adapter](../../runtime/agents/identity.py) verifies RS256 through locked
`google-auth`, requiring exact HTTPS issuer, single audience, known key ID, JWT
type, bounded input, integer issued/expiry/not-before times, at most one-hour
token lifetime and no expired public-key snapshot. Duplicate JSON claims, remote
key URLs, algorithm substitutions and stale snapshots fail closed. There is no
request-selected discovery URL, token fetch, ADC or service-account credential.
The [official decoder contract](https://google-auth.readthedocs.io/en/latest/reference/google.auth.jwt.html)
supports certificate-map verification and audience/time checks; issuing-authority
claims are constrained additionally by the candidate.

Trusted startup subject grants determine tenant and profile capabilities from the
authoritative registry. Token scope/tenant-ID fields grant nothing. HMAC tenant
references preserve the existing pseudonymous invariant. Expired trust/revoked
subject/profile grants deny requests; conversations recheck the same existing
identity/tenant/profile binding. This adapter is not wired into the offline UI.
Local RSA signing proves signature verification behavior, **not** a real issuer
login or production authentication. No private signing key is written to source.

The unwired adapter now has monotonic operator-only `revoke_subject` denial.
Existing tokens, resolved contexts and conversation ownership rechecks deny the
revoked subject; another subject's server-side grants stay unchanged. There is no
browser revocation/grant endpoint. This process-local denial neither revokes issuer
tokens nor proves durable revocation after restart; a real issuer/session gate remains.

Still required: select the actual owner/application issuer, audience and permitted
subjects; independently verify its published keys and token profile, transport,
revocation and session lifecycle. Refresh trusted public snapshots out of band
before expiry; no browser-directed JWKS fetch. Real issuer login and key-rollover
evidence remain absent. Do not use operator Google credentials as user identity.

## Credential ownership and lifecycle

[Candidate contracts](../../runtime/agents/credentials.py) prepare non-admin-owner
issuance payloads: one-hour duration, alias `secure-financial-chat`, exact
`/chat/completions`, four requests/minute, 8,192 tokens/minute, USD 0.50/key proposed
budget, separate profile metadata. These are request shapes, **not** proof that a
gateway issued or enforced keys. No administration endpoint is called. Owner/team
inheritance must be verified; a proxy-admin-owned virtual key is not an acceptable
substitute. See [LiteLLM virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys).

The prepared agent factory receives only profile-specific startup keys:
`PORTFOLIO_LITELLM_INFRASTRUCTURE_CLIENT_KEY` and
`PORTFOLIO_LITELLM_FINANCIAL_CLIENT_KEY`. Generic key fallback is removed **from
this factory**, while the existing general Phase 3 adapter retains its contract.
Presence of administrative/provider credential environment names rejects agent
startup; the factory never reads the administrative value. Provider identity and
administrative key belong exclusively to gateway/operator processes. No browser
input changes any credential, endpoint, model or profile.

`ScopedCredential` supplies local expiry/revocation/rotation checks, with private
representation. It is an unwired candidate guard, not database/server revocation
or a deployed renewal service. Operator must delete/revoke the server key first,
verify denial, then issue a replacement; failed rotation leaves the old handle
unusable. Revoke on completion/failure, expire within one hour, remove private
startup material, and verify denial after cleanup/disconnect recovery.

Environment checks cannot prove filesystem/process isolation. Deployment must
deny app access to gateway/admin/Google credentials, metadata identity, key database
and credential mounts. Private PostgreSQL, exact minimum DB roles, per-profile
route/model/expiry/rate/token/spend denial and cross-profile-key evidence remain
required. The [unwired budget wrapper](../../runtime/agents/gateway_budget.py)
reserves each dispatch before HTTP, including failures, across profile/conversation
resets: 32 attempts per run, 16 per trusted subject, at most one hour. It preserves
the existing measured counters and does not fabricate provider receipts or cost.
Local expiry/revocation blocks before dispatch. Process restart does not establish
durable quota enforcement; a reviewed ledger/owner takeover gate remains. No
current key/database has been created.

`ScopedHTTPGateway` now constructs the real existing HTTP adapter from the exact
checked scoped handle. It rejects administrative/provider environments and
unbounded timeout, checks key continuity before every dispatch, and preserves the
same run budget when a revoked key is replaced. A guard for one key cannot silently
authorize another cached adapter key. Actual loopback HTTP tests cover this
composition without cloud/model traffic; they are not LiteLLM virtual-key issuance
or server route/model/expiry/spend enforcement evidence.

Current read-only source inspection of the exact retained proxy confirms virtual
key authentication raises `No connected db.` (HTTP 400) when `prisma_client` is
absent, before regular virtual-key lookup. No in-memory allowlist, custom-auth bypass
or administrator key substitution was added to conceal this blocker. A qualified
private PostgreSQL/key lifecycle is still required; no new gateway image design,
database, credential or server key was created in this context-policy preparation.

## Two bounded gateway candidates

Retained committed gateway scan: Wolfi OS/CPython, pip, Node/npm and many proxy
dependencies; 82 HIGH/five CRITICAL and duplicate evidence fail the unchanged
policy. Original report is preserved, not deduplicated into acceptance. A minimal
Python/distroless proxy design omits the OS package manager, Node toolchain and
admin UI build, pins official `litellm[proxy]` 1.104.0 and exact corrected PyJWT/
cryptography versions, and hash-locks its complete resolver output. The first
candidate passed the vulnerability policy but failed isolated proxy startup:
`libffi.so.8` was absent. The final candidate adds that exact native dependency
and explicitly locks gateway-only `google-auth` for the
[Vertex authentication boundary](https://docs.litellm.ai/docs/providers/vertex).
Both candidates/evidence are retained; no third design or tag-update loop follows.
Candidate dependencies are not installed in the existing UI environment.

[Dockerfile](../../docker/litellm-candidate/Dockerfile) uses the already assessed
immutable Python 3.12.15/Distroless Debian 13 bases, nonroot 65532, immutable locks;
read-only/no-network smoke tests and fresh SBOM/Trivy/KEV/policy evidence are required.
The upstream [proxy installation](https://docs.litellm.ai/docs/simple_proxy) supports
the proxy package; pinning a package alone does not prove provenance or security.
The [upstream incident record](https://github.com/BerriAI/litellm/issues/24518)
is an additional supply-chain review gate; affected historical versions are not
selected. Maximum two materially different designs, no tag-update/scan loop.

The [qualification record](../../evaluation/litellm-candidate/qualification.json)
reports the actual candidate subject and gates. A local configuration digest is
not a registry manifest or signature. No committed Kubernetes gateway image,
vulnerability evaluator, exception register or redaction authority is changed.
Image-policy acceptance alone is not a functional production gateway qualification.
Actual proxy/provider-stub protocol, database/key and TLS/egress gates are separate.

Fresh final evidence: matching archives/configurations from two fresh builders,
zero HIGH/CRITICAL, 16 MEDIUM/eight LOW, 1,687 SBOM components; copied native package
versions and full source scan are retained separately. The actual network-none
proxy boots with a gateway-only dummy administrative configuration and refuses
startup without it. Existing AgentCore correctly rejects an actual gateway mixed
with offline simulation. An unissued dummy client probe returns HTTP 400 and zero
provider-stub calls; this **does not pass** the requested 401/403 authentication
denial gate or virtual-key qualification. No server key/database was issued or
bypassed. Actual end-to-end proxy tool decisions remain unproven; the separate
local HTTP protocol fixture tests still pass. Logs contain no real credentials.

## Model protocol and live gates

Local HTTP stubs exercise the existing canonical decision/schema envelope and
registry tool proposals, measured HTTP attempts/responses, unavailable/malformed
token usage, sanitized failures, limits and no retries. They do not measure actual
Gemini compliance, real redaction, provider receipts or billed cost. No mock
redaction is labelled a qualified live secure path. Real requests must pass through
LiteLLM only, never a provider SDK in an agent.

The intended Vertex model proposal must be reverified for availability/retirement,
entitlement, structured output, Arabic behavior, quota, pricing and processing
location before a future approval. No model upgrade is silently selected here.
Exact gateway-only keyless identity/trust/IAM/network, application issuer, durable
sanitized fail-closed audit, scoped key enforcement and qualified redactor remain
hard gates. Existing SDP IAM and exhausted SDK approval authorize none of these.
See the [follow-up boundary](live-follow-up-bundle.md) for the retained limits.
