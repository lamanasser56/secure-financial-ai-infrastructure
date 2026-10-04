# Google SDP synthetic text evaluation plan

**Status, 2026-10-04:** The separately approved us-east1 signed release and one nine-case synthetic GKE execution completed: six PASS, zero FAIL, three INCONCLUSIVE; 18 SDK attempts, zero retries. Temporary evaluation resources were removed and the node identity disabled. The adapter remains disabled/unwired in the agents; replacement readiness is unproven. Presidio remains authoritative. The [agent qualification and conditional retirement plan](google-sdp-agent-qualification-plan.md) records actual evidence and supersedes the next action. Further Presidio remediation is paused. Preserve [ADR-004](../architecture/decisions/ADR-004-bounded-google-sdp-evaluation.md) and [ADR-005](../architecture/decisions/ADR-005-us-east1-synthetic-sdp-evaluation.md) as historical decisions.

## Scope and execution authority

The new [agent preparation checkpoint](google-sdp-agent-preparation-checkpoint.md)
and [coverage matrix](google-sdp-agent-coverage.md) are separate from this historical
seed. Candidate robustness/deadlines and fresh image evidence do not promote it;
the full eight-class campaign remains blocked. The historical three observation-only
cases and 18-attempt result are not reclassified or rerun.

Compare Presidio and Google Sensitive Data Protection (Google SDP) offline against the same reviewed, generated synthetic-text cases. Google SDP is disabled by default and limited to non-production text evaluation in South Carolina `us-east1` through `dlp.us-east1.rep.googleapis.com`. Future execution requires separately reviewed identity, IAM, regional routing, budget, and test authorization. Never use a global endpoint, cross-region or automatic global fallback, silent endpoint substitution, or a request-selected endpoint. Invalid or unavailable regional configuration fails closed.

The [candidate adapter](../../runtime/phase3/google_sdp_adapter.py) has offline fake-client tests and was exercised by the separately approved evaluation Job. It is not wired into the authoritative `TrustedRuntime` or agent factories. Its fixed endpoint and trusted constructor project identity cannot be selected from request text or metadata. The bounded GKE run used Application Default Credentials and the approved Workload Identity/IAM path; that does not authorize future deployments. The adapter accepts no API key or credential file. It requests inspection before de-identification on the same regional client, with retries disabled and no global or cross-region fallback. Only closed neutral categories and redacted text leave the adapter. Failures emit `redaction:provider_failure` without raw values or provider details.

The historical seed used a 20-second RPC deadline. The current unwired candidate
uses three-second RPC deadlines within an eight-second monotonic overall budget
and separates actual SDK attempts from injected-client tests. The live harness
still accepts only the committed seed corpus; its completed run exhausted nine
inspect and nine deidentify attempts with no retry. Current bounds and three-category
coverage do not qualify the full agent redaction boundary. The
[milestone readiness record](google-sdp-milestone-readiness.md) preserves historical
preparation; the superseding agent plan defines the next gates.

The candidate currently configures only Google's generic email, phone, and payment-card infoTypes. This is an API shape for offline boundary tests, not evidence that those detectors work in the selected region or on any specific language or identifier. A separate Change Set is required for live API execution, IAM, runtime wiring, or an authority change. No Saudi, Arabic, Iqama, national-ID, commercial-registration, OCR, mixed-script, regulatory, production, or Presidio replacement claim follows from this adapter.

No customer or production data, real financial records, real tenant or personal identifiers, invoices, documents, uploaded files, images sent to Google SDP, or production OCR content are permitted. Only synthetic textual output from an upstream OCR simulation may be tested; this plan makes no claim about Google SDP image or OCR availability in the selected region. No compliance or real-world accuracy claim follows from these tests.

## Corpus design

The committed [seed corpus](../../evaluation/google-sdp/corpus.json) is machine-labelled and deterministic. Its required-detection cases use only synthetic email addresses at RFC-reserved example domains. Negative controls and observation-only cases cover surrounding text, repetition, punctuation, whitespace and conservative obfuscation without guessing real identifier formats. [Corpus validation](../../evaluation/google-sdp/corpus.schema.json) rejects unknown configuration fields and duplicate case IDs. The [offline runner](../../scripts/evaluate-google-sdp.py) validates the corpus by default and constructs no provider client. It emits only the fields permitted by the [result schema](../../evaluation/google-sdp/result.schema.json); no raw or redacted fixture text is committed as a result artifact.

Google's [infoType documentation](https://docs.cloud.google.com/sensitive-data-protection/docs/concepts-infotypes) identifies `EMAIL_ADDRESS`, `PHONE_NUMBER` and `CREDIT_CARD_NUMBER` as generic detectors. This seed asserts required detection only for synthetic `EMAIL_ADDRESS` cases. Phone and payment-card accuracy remains observation-only because this Change Set does not create telephone or checksum-valid card values.

Live execution requires both `--live` and the exact `PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK=I_ACKNOWLEDGE_SYNTHETIC_ONLY_GOOGLE_SDP_EVALUATION` environment value, plus a separately supplied trusted project identity. Neither control is set in CI. The runner has no endpoint, region, credential or provider argument; the adapter reads `us-east1` and `dlp.us-east1.rep.googleapis.com` only from the committed deployment contract at startup. Offline success proves only schema, sanitization and harness behavior. Even fake-client case passes cannot award **PASS FOR FURTHER BOUNDED INTEGRATION**, because the existing security, detection quality, operations and image gates remain unproven. A case failure yields **FAIL AND RETAIN PRESIDIO**; otherwise the runner records **INCONCLUSIVE — MORE EVIDENCE REQUIRED** for later review.

The small seed does not establish phone, payment-card, Saudi identifier, Arabic OCR, image or corruption accuracy. Those categories are marked deferred or observation-only, without live detector claims. A future expanded corpus generator must create data specifically for this evaluation, without copied public or private person data. Use clearly synthetic names and reserved domains such as `example.com` and `example.org`. Avoid numbers that could reasonably belong to real people or organizations. Review every generated case before any API call; exclude real or uncertain data. Expanded cases must carry a machine-readable `synthetic: true` label and the following fields:

| Field | Purpose |
| --- | --- |
| `case_id` | Stable synthetic-case reference |
| `synthetic` | Machine-readable synthetic-data assertion |
| `language` | Arabic, English, or mixed |
| `script` | Arabic, Latin, mixed, or numeral variant |
| `category` | Identifier or negative-control category |
| `input_template` | Generation template, without real values |
| `expected_entity_types` | Reviewed expected detections |
| `expected_action` | Redact, retain, or reject |
| `negative_control` | Whether detection would be a false positive |
| `notes` | Generation and review rationale |

Create paired cases for both candidates covering English, Arabic, mixed Arabic/English, right-to-left text, punctuation-adjacent identifiers, multiple and repeated identifiers, extra whitespace, line breaks, Unicode normalization, Arabic and Western numerals, mild obfuscation, synthetic OCR-like corruption, and false-positive controls. Include empty and oversized input boundaries and simulated malformed responses, timeouts, and regional endpoint failures. Preserve expected spans or actions for each candidate without relaxing the provider-neutral redaction contract.

## Detector candidates and restrictions

The labels below describe proposed evaluation approaches, not verified Google feature availability or regulatory validation. Verify any built-in candidate and its regional availability before use.

| Information category | Proposed classification | Restriction |
| --- | --- | --- |
| Person names, email addresses, IP addresses, payment-card-like strings | Built-in candidate detector | Verify actual support; use generated synthetic text only. |
| Phone-like strings | Built-in candidate detector | Detection is not regulatory or ownership validation. |
| Generic IBAN-like strings | Built-in candidate detector | Verify support; Saudi IBAN cases require safely generated fixtures. |
| Saudi IBAN-like strings | Locally validated deterministic pattern | Document safe fixture generation and test the pattern before any comparison. |
| VAT-like strings, financial account references, invoice-reference-like strings | Custom detector candidate | Require an authoritative source, tests, and review; a match is not regulatory validation. |
| Saudi national-identifier-like and Iqama-like strings | Deferred pending authoritative format | Support and safe generation rules are unproven; do not invent checksums or patterns. |
| Saudi commercial-registration-like strings | Deferred pending authoritative format | Detection is deferred; do not invent a format or checksum. |

Any future custom detector needs an authoritative format source, safe synthetic-generation rules, negative tests, and security review. The current repository does not establish Google built-in Saudi detectors or Arabic, Saudi-identifier, commercial-registration, image, or OCR accuracy.

## Evidence and gates

Only reviewed generated synthetic fixtures may be committed; preserve the seed unchanged and prepare any expanded corpus separately. Raw provider outputs belong only in an approved private evaluation workspace and must never appear in logs, traces, exception messages, LiteLLM metadata, audit envelopes, Git, or shared reports. Before new execution, approve exact corpus, scoring and operational thresholds. Historical release/signature/network and one synthetic-run gates passed within their bounded scope; broader agent qualification remains open. See the [live runbook](google-sdp-live-runbook.md) and superseding agent plan.

| Gate | Required evidence for a future pass |
| --- | --- |
| Security | No raw mandatory high-risk test value remains in a successful redacted output or appears in telemetry; every validation or redaction failure causes zero LiteLLM requests; global/cross-region configuration is rejected; no static Google credential is required. |
| Detection quality | Record precision, recall, false negatives, and false positives separately for Arabic, English, mixed script, obfuscated text, OCR-corrupted synthetic text, and each identifier category. Require zero false negatives for mandatory high-risk cases in the approved bounded corpus. This does not establish real-world accuracy. |
| Operations | Measure latency, timeouts, failure rate, regional endpoint behavior, response-schema stability, request-size behavior, and estimated evaluation cost against limits approved before execution. Do not infer results from this plan. |
| Portability and rollback | Keep Google types behind a provider-neutral contract. Preserve Presidio source until separate retirement approval; any live rollback image must pass policy. The blocked candidate is not an accepted rollback. No automatic fallback within a request. |
| Image qualification | The [evaluation image](../../docker/google-sdp-evaluation/README.md) had passing local and registry qualification and exact-digest signature verification in the historical run. Changed image/config/corpus requires fresh evidence and authorization. The [release workflow](../../.github/workflows/release-google-sdp-evaluation.yml) and [Job templates](../../kubernetes/apps/google-sdp-evaluation/README.md) remain contracts, not proof of agent integration. |

The historical evaluation exercised GKE Workload Identity → Google IAM → regional SDP for that bounded corpus. Future identities and runs require their own reviewed bundle. Static service-account keys, embedded/Git credentials, LiteLLM keys and application-managed provider secrets are prohibited on this redaction path. A future integrated adapter must fail closed on configuration, authentication, authorization, availability, response, completeness or policy failure, with zero subsequent LiteLLM requests.

## Decision record

After review, record exactly one outcome: **PASS FOR FURTHER BOUNDED INTEGRATION**, **FAIL AND RETAIN PRESIDIO**, or **INCONCLUSIVE — MORE EVIDENCE REQUIRED**. None authorizes automatic production cutover, Presidio deletion, customer-data processing, production deployment, or a compliance claim. A pass still requires a separate ADR and Change Set before Google SDP could become authoritative.

IAM, registry publication, GKE execution and a synthetic live API call may proceed only under an explicitly approved integrated execution bundle with all prerequisites satisfied. A provider authority change still requires its own reviewed decision and integration. AWS and Azure candidates could reuse the same sanitized result contract through the neutral `RedactorClient` boundary; no such adapter is implemented here.

The [synthetic execution proposal](google-sdp-synthetic-execution-proposal.md) is the historical scope approved and executed once, including the owner-review and native IP/port amendments. Its pre-execution status text is retained history; it does not approve another run. Owner approval is not independent review; DNS-derived IP/port enforcement is not Layer-7 shared-hostname isolation. No production or provider-authority gate passed.

## Superseding the historical region

[ADR-005](../architecture/decisions/ADR-005-us-east1-synthetic-sdp-evaluation.md) selects South Carolina for this synthetic evaluation amendment. [ADR-004](../architecture/decisions/ADR-004-bounded-google-sdp-evaluation.md)'s Dammam region is superseded history; all data and authority prohibitions remain. The [deployment contract](../../evaluation/google-sdp/deployment.json) is closed and image-bound. Processing parent is `projects/PROJECT_ID/locations/us-east1`; invalid or missing configuration fails closed with no SDK construction. No automatic migration, request-selected location, fallback, live authorization or Saudi-residency claim is introduced. The original Dammam approval does not authorize execution of this amended bundle.
