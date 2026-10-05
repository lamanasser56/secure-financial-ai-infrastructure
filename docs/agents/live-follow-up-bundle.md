# Bounded live-agent execution boundary

## Checkpoint: technically blocked

The separately accepted [context-pattern candidate](../architecture/decisions/ADR-007-context-pattern-redaction-candidate.md)
now has its own [SDP-only execution proposal](../security/google-sdp-context-execution-bundle.md)
and fresh offline image evidence. That proposal does not include live agents,
Vertex, key issuance or a provider-authority change. This live-agent boundary remains
blocked on independent identity/gateway/audit and broader redaction acceptance.

See the [current independent preparation](identity-and-gateway-preparation.md),
[per-class research decision](../security/google-sdp-provenance-decision.md) and
[proposed scope ADR](../architecture/decisions/ADR-006-redaction-qualification-scope.md).
Candidate signature validation/server grants and scoped-key request/lifecycle
contracts are implemented locally. Actual issuer, key database/enforcement and
gateway/provider qualification are not supplied by those tests. Full replacement
qualification remains blocked; this document is not an executable bundle.

**Direction update, 2026-10-04:** Presidio remediation and this bundle's proposed
real-Presidio service path are paused by owner instruction. Preserve source and
candidate evidence; Presidio remains authoritative. The
[SDP qualification plan](../security/google-sdp-agent-qualification-plan.md)
supersedes that next action with conditional integration/retirement. Gateway,
identity, tenant, audit, model and budget gates remain independent requirements.

The [SDP preparation checkpoint](../security/google-sdp-agent-preparation-checkpoint.md)
now supplies adapter robustness, exact partial fixture provenance, frozen scoring
and fresh candidate image evidence. It makes a precise BLOCKED decision for the
full campaign. The [consumer inventory](../security/google-sdp-agent-integration-retirement.md)
defines subsequent conditional steps; neither selects SDP nor retires Presidio.

Local preparation is complete for the independent changes in the
[handoff](live-preparation-status.md). **Do not execute this bundle or request
approval for unspecified resources.** Redactor qualification, gateway functional/
credential/provenance gates and real identity prerequisites remain unresolved.
The [Presidio qualification artifact](../../evaluation/presidio-bounded/qualification.json)
contains exact locally assessed image subjects; all are unpromoted. The final
local source commit and worker validation evidence are recorded in the owner
handoff. No GitHub push is authorized for this milestone.

Preserve the existing conversation UI, Arabic/English views, free-text questions,
ephemeral context, read-only profiles, tenant isolation and deterministic finance.
The UI/CLI remain offline simulations. No old SDP execution approval supplies
Vertex calls, an agent budget, new identities or new persistent services.

## Exact source and artifact boundary

| Input | Selection and status |
| --- | --- |
| Completed conversation baseline | `de4325c36bfdbb0a9522b89269affb9ea919a187` |
| Prepared integration source | Local commit containing this bundle; exact SHA in final handoff; not pushed |
| Presidio bounded candidate | Local configuration digest `sha256:016631eb3baa6df8d81031720de99776f493ea52259c6bca3ce61967c2887efa`; 31 actual HTTP cases PASS, 47 HIGH findings BLOCK |
| Existing gateway reference | `ghcr.io/berriai/litellm@sha256:cae1ac3492d6d0bea69c26f4485381624e073eb753f3534ae7703a4204a4ce6b`; fresh assessment blocked |
| New gateway candidate | Local configuration `sha256:7b3726dbebb2f67eb376c2ce89793e62166a0f1c16174dd1aeed424ae359bd7d`; unchanged image policy/reproducibility PASS; unpublished/unsigned; keys/database/protocol unqualified |
| Presidio upstream alternatives | Exact committed/new upstream digests and findings in the qualification artifact; none accepted |
| Retained SDP image | Separate signed evaluation image with source e5ddb647; not a redactor or agent/gateway image; no reuse as agent provenance |
| Runtime locks | Existing dev/Presidio/SDP locks unchanged; separate `requirements-agent-identity.in/.txt` and `requirements-litellm-candidate.in/.txt` for isolated candidates |

The local candidate has no registry manifest subject or signature. Its configuration
bytes are verified against the actual Docker archive. The original scan is retained;
a labelled policy copy binds the archive subject to that configuration digest.
Any image-content change requires new scan/SBOM/KEV/policy and behavior evidence.
No signing, publishing or expected-digest substitution is part of preparation.

## Resources and prerequisite differences

| Resource boundary | Existing reuse / proposed exact local boundary | Execution gate |
| --- | --- | --- |
| Worker | Existing `secure-infra-worker`; isolated checkout; preserve dirty original | No VM identity, firewall, disk or MASAR modification |
| Offline UI | Existing loopback `127.0.0.1:8765`, SSH access | Still simulated; no live toggle |
| Future agent application | Same private listener after separately qualified identity/core wiring | Qualified source, issuer/audience and trusted capability/tenant map absent |
| Future gateway | Private `127.0.0.1:4000`; alias `secure-financial-chat` only | Qualified LiteLLM digest/provenance, real no-retry and key-denial evidence absent |
| Future real redaction | Private `127.0.0.1:5001` / `127.0.0.1:5002` | Candidate policy must pass; no promotion of blocked image |
| Future key database | Dedicated private PostgreSQL on `127.0.0.1:15432`, database `agent_gateway_qualification` | Exact qualified image/role/temporary-volume plan absent; no reuse of product tables |
| Future audit | Private bounded sanitized-event destination, proposed seven-day retention | Durable fail-closed delivery/cleanup not implemented |
| Vertex API | `aiplatform.googleapis.com` already enabled: read-only project check | Model entitlement/quota and gateway identity remain unproven |
| GCP resources | No new cluster, bucket, registry, VM, IAM grant or workflow selected/applied | Exact identity transport/resource diff must be resolved before a saved-plan approval |

The reviewed project is supplied privately by the owner; environment-specific
project/account values are not imported into source. Existing SDP GSAs, WIF
source-SHA trust, registry policy, retained state and deleted cluster are outside
this integration. Do not use those identities or approvals as model authority.

## Identity, IAM and credentials

The current UI uses startup-selected simulated personas and fixture tenants. Its
SSH/loopback boundary does not independently authenticate other local processes.
Conversation cookie, CSRF and opaque handle bind the server-resolved identity,
tenant and profile; these are confinement controls, not production login.
The live factory continues rejecting simulated identity and redaction doubles.

A future execution must configure the prepared application `Authenticator`,
`TenantResolver` and `Authorizer` candidate with actual trusted issuer, audience,
verified public-key snapshot and subjects. Signature/expiry validation and fixed
server-side mapping are locally implemented; real login/rollover/revocation,
deployment transport and reset-independent identity quota remain unproven. No request/browser can
choose identity, tenant, profile capabilities, provider URL, model or credentials.
Synthetic tenant mapping stays explicitly synthetic, even with genuine login.

For the gateway alone, the proposed principal name is `portfolio-agent-gateway`
(GSA not created). Google [access-control documentation](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/access-control)
lists `aiplatform.endpoints.predict` for prompt requests. Read-only project testing
listed that permission. Custom-role eligibility and an exact keyless trust route
must still be verified. No broad `roles/aiplatform.user`, administrator role,
operator credential reuse, static JSON key or impersonation grant is applied.
There is no reviewed binding/principal transport to authorize yet. A concrete
future IAM plan must enumerate the exact role, project, subject and trust conditions;
no wildcard or existing SDP WIF reuse may be inferred from this proposal.

The application needs two separately scoped, short-lived virtual keys: one per
agent profile, only `/chat/completions` and `secure-financial-chat`, no administrative
routes, no model override, no retries/fallback, one-hour maximum expiry, rate/token/
spend limits shared with an identity-wide run ceiling. Generate them through the
operator-only gateway admin boundary, store only in private startup handling and
never browser/source/reports. Revoke both after qualification or first failing gate;
rotate by revocation/new issuance, never reuse expired qualification keys.

The general Phase 3 `PORTFOLIO_LITELLM_CLIENT_KEY` contract has no master-key fallback.
The prepared agent factory now requires a separate profile-specific startup key,
and rejects administrative/provider credential environments without reading their
values. Filesystem/identity isolation remains a deployment gate. The gateway alone owns
`PORTFOLIO_LITELLM_MASTER_KEY` and Google workload identity. Key inequality does
not prove scope: actual denied route/model/expiry/spend tests are mandatory.
The [virtual-key documentation](https://docs.litellm.ai/docs/proxy/virtual_keys)
describes the PostgreSQL-backed boundary. No keys/database were created here.

## Proposed provider selection, verified official capability and limits

The intended provider remains Gemini through Vertex AI via LiteLLM `vertex_ai/`.
No direct provider SDK is added. Proposed bounded model: **`gemini-2.5-flash`**, regional
request location **`us-east1`**, endpoint `us-east1-aiplatform.googleapis.com`.
This is a proposal, not a silently selected replacement for an approved model.
The repository gateway still has trusted deployment placeholders.

Google's [model reference](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash)
lists structured output, function calling and us-east1 availability. It also lists
retirement on **2026-10-20** and US multi-region ML processing. Regional endpoint
availability is not proof of South Carolina-only processing. This proposal expires
before retirement; reverify availability/entitlement immediately before any approved
run. Do not migrate to global/newer models automatically. No Saudi-residency claim.

The existing HTTP adapter uses JSON decisions inside the closed Phase 3 envelope;
it does not execute native function calls. Canonical tool purposes and input schemas
are now supplied. Actual Gemini decision compliance, Arabic answers, malicious/
malformed output containment and gateway translation remain untested. Unsupported
scope must refuse; unavailable periods must return no invented expense report.

Keep all [existing limits](architecture.md): four model/four tool attempts and 60
seconds per turn; model stage 20 seconds, tool/identity/governance two seconds,
redaction ten seconds; 500 characters/1,500 UTF-8 input bytes; 4,000-byte model prompt;
4,096-byte tool/final JSON; bounded response/context. Eight turns, sixteen model/
twelve tool attempts, 240 execution seconds and fifteen-minute nonrenewing session
per conversation remain. Explicit calendar/source slots clarify before tools and
never guess an old/relative month. Reset is not a live account-wide budget control.

The adapter now fixes `max_tokens=1024`; gateway/model enforcement, including any
thinking tokens, must be proven. Router/provider retries, fallbacks, streaming,
parallel calls, search/URL/code tools and request-selected provider options stay
forbidden. All provider requests must pass through the qualified gateway.

## Network and service lifetime

Keep every local listener private and use authenticated SSH forwarding. Local HTTP
is proposed only on the same worker loopback; it is not encrypted host/process
isolation. Separate containers/process credentials and qualified real authentication
are required before calling that path secure. Remote/provider traffic needs verified
TLS, regional endpoint pinning and gateway-only credential access. Redirects and
ambient proxies remain disabled in the application HTTP adapter.

There is no new network-enforcement evidence for this model bundle. The prior GKE
SDP DNS-derived IP/port tests do not prove gateway containment. No firewall/public
port/IAM change was made. A future gateway host/identity route needs exact reviewed
egress/DNS/TLS controls and genuine allow/deny tests before live calls. Application
URL pinning alone is not infrastructure-level FQDN or credential-store isolation.

Proposed temporary service lifetime: one hour; begin cleanup by minute 45 and
immediately on a required-control failure. An operator starts/verifies cleanup;
there is no automatic guarantee after disconnection. The owner must take over.
No Kubernetes Job TTL is described as host/service cleanup.

## Committed synthetic qualification matrix

These are intended cases for one future approved run, not executed provider calls.
Local protocol fixtures exercise the same shapes without provider access.

| Scenario ID | Case and required evidence |
| --- | --- |
| infra-en-docker-config | Exact approved synthetic CI/runbook diagnosis; failure/cause/IDs/repair/unverified points; image fixture supplemental |
| infra-ar-archive | Arabic question/answer with unchanged technical IDs and approved source; no executed repair |
| finance-en-january | Trusted tenant summary/ranking; 24,000 minor units = SAR 240.00, software 200.00, transport 40.00 |
| finance-ar-clarify | Missing month then explicit Arabic January 2026 reply in the same conversation; zero tool/model HTTP attempts before slot completion |
| finance-no-march | Unavailable March data; one summary lookup at most, no invented totals/categories |
| pre-model-denials | Wrong identity/context, other session/tenant/profile, endpoint/credential overrides; zero gateway HTTP attempts |
| post-model-denied-tool | A forbidden proposal after one gateway reply; preceding attempt retained, zero forbidden-tool executions |
| malformed-output | Invalid decision/unknown fields/citations; no unauthorized tool and no partial unsafe answer |

The eight scenario IDs include a clarification follow-up and separately bounded
negative vectors. Proposed **global ceiling**: 32 model HTTP attempts and 32
read-only tool attempts across the entire run, regardless of conversation resets;
zero automatic retries. Stop before dispatch if a remaining budget cannot cover
the next turn. Model-generated forbidden/malformed proposals are not guaranteed;
controlled local injection proves coordinator behavior, while future observed live
behavior must be reported separately rather than fabricated.

The live corpus may contain only synthetic approved questions/fixtures. No real
financial records, customer identifiers, uploads or raw operational credential/log
material. Retain only scenario/config/version/evidence IDs, control outcomes,
actual attempts and validated available usage; never replay raw conversations,
model answers or protected tool results. Invalid/missing usage and actual cost are
unavailable. A gateway response does not independently prove upstream receipts;
transport failure must not be reported as zero provider activity.

## Cost and cleanup proposal

Official [standard text pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)
for the proposed model lists USD 0.30/M input tokens and USD 2.50/M output tokens,
including reasoning. An illustrative 32 requests at 4,096 input and 1,024 output
tokens each gives about **USD 0.122 model cost**. This is an estimate using assumed
token counts, not measured usage, an enforced input-token cap or a guaranteed bill.
Existing worker, retained state/registry and MASAR costs are outside that estimate;
new service disk/log/network and any verified identity-host resources must be priced
before their authorization. No new cloud resources are presumed free.

Proposed incremental operator stop threshold: **USD 1**, separate from the completed
SDP USD 5 milestone. Not inherited approval, not an automated cap. Identity-wide
quotas, key expiry/spend enforcement and operator timing must be qualified before
approval. No billed live usage was observed in this preparation.

On any approved-run finish/failure: revoke both client keys, stop temporary gateway/
real-redactor/application/database processes, remove private credential files and
temporary key database volumes, verify loopback listeners/processes are absent,
restore explicitly temporary IAM to its saved prior state, and verify any newly
owned cloud-resource deletion. Preserve the existing offline demo and original
worker/MASAR resources. Retain sanitized qualification/event summaries for the
reviewed seven days; no transcript/token retention. No current local candidate
container remains running after preparation. Actual cloud/IAM cleanup instructions
require the still-missing exact resource plan; never delete unrelated retained SDP
resources or apply an incomplete plan.

## Required gates before one execution checkpoint

1. Complete separately bounded SDP qualification and a reviewed provider-selection
   decision before conditional integration. Presidio remediation is paused; no
   blocked candidate is a live fallback. Detector success does not override image,
   privacy or runtime policy.
2. Qualify the exact gateway image and valid complete policy evidence, scoped keys,
   no-retry translation, private database and sanitized audit delivery.
3. Supply real issuer/audience/subject/tenant mapping and verify isolation; select
   a gateway-owned keyless identity route and exact IAM/API/resource plan.
4. Reverify supported model/location, project entitlement/quota, token/cost controls
   and native network/TLS boundaries without an unapproved model request.
5. Present exact final source/image/identity/resource values and a successful
   saved plan for any mutations, plus this scenario/limit/cleanup contract, once.

Those gates remain unmet. No execution approval is requested at this blocked
checkpoint. No production readiness, comprehensive detection, Saudi residency,
full portability, independent review or CS6 closure is established.

## Frozen context campaign continuation — 2026-10-05

The single context-001 diagnostic passed and its temporary cleanup was verified.
This does not establish the original failure cause or broader detection quality.
The [current full campaign preparation](../security/google-sdp-context-campaign-execution-bundle.md)
reuses the repaired adapter for exactly 70 mandatory cases plus 16 unsupported
observations, at most 172 content attempts and zero retries. Its fresh image
record remains unpromoted; publication and execution need separate owner approval.
The USD 5 threshold and billing screenshot prerequisite are removed by owner
amendment; billing must not be upgraded or changed. No Presidio remediation or
separate valid-identifier/eight-class research resumes. Provider authority, offline
UI, agent/model enablement and retirement remain unchanged. Exact subsequent
scope/privacy/runtime/audit/identity/gateway/integration/authority gates are listed
in that proposal; a finite policy pass does not close them.
