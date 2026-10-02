# Google SDP synthetic text evaluation plan

**Status:** Disabled offline adapter implemented; no Google API call, synthetic corpus execution, IAM grant, deployment, accuracy qualification, or production integration has occurred. This plan follows [ADR-004](../architecture/decisions/ADR-004-bounded-google-sdp-evaluation.md). Microsoft Presidio remains the authoritative redactor and default runtime path.

## Scope and execution authority

Compare Presidio and Google Sensitive Data Protection (Google SDP) offline against the same reviewed, generated synthetic-text cases. Google SDP is disabled by default and limited to non-production text evaluation at Dammam `me-central2` through `dlp.me-central2.rep.googleapis.com`. Future execution requires separately reviewed identity, IAM, regional routing, budget, and test authorization. Never use a global endpoint, cross-region or automatic global fallback, silent endpoint substitution, or a request-selected endpoint. Invalid or unavailable regional configuration fails closed.

The [candidate adapter](../../runtime/phase3/google_sdp_adapter.py) exists only for offline, fake-client contract tests. It is not wired into `TrustedRuntime`, production factories, or Kubernetes. Its fixed endpoint and trusted constructor project identity cannot be selected from request text or metadata. A real client would use Application Default Credentials through the optional Google library; a future GKE deployment would require separately reviewed Workload Identity and IAM. The adapter accepts no API key or credential file. It requests inspection before de-identification on the same regional client, with retries disabled and no global or cross-region fallback. Only closed neutral categories and redacted text leave the adapter. Failures emit `redaction:provider_failure` without raw values or provider details.

The candidate currently configures only Google's generic email, phone, and payment-card infoTypes. This is an API shape for offline boundary tests, not evidence that those detectors work in Dammam or on any specific language or identifier. A separate Change Set is required for a reviewed synthetic corpus, live API execution, IAM, runtime wiring, or an authority change. No Saudi, Arabic, Iqama, national-ID, commercial-registration, OCR, mixed-script, regulatory, production, or Presidio replacement claim follows from this adapter.

No customer or production data, real financial records, real tenant or personal identifiers, invoices, documents, uploaded files, images sent to Google SDP, or production OCR content are permitted. Only synthetic textual output from an upstream OCR simulation may be tested; this plan makes no claim about Google SDP image or OCR availability in Dammam. No compliance or real-world accuracy claim follows from these tests.

## Corpus design

The committed [seed corpus](../../evaluation/google-sdp/corpus.json) is machine-labelled and deterministic. Its required-detection cases use only synthetic email addresses at RFC-reserved example domains. Negative controls and observation-only cases cover surrounding text, repetition, punctuation, whitespace and conservative obfuscation without guessing real identifier formats. [Corpus validation](../../evaluation/google-sdp/corpus.schema.json) rejects unknown configuration fields and duplicate case IDs. The [offline runner](../../scripts/evaluate-google-sdp.py) validates the corpus by default and constructs no provider client. It emits only the fields permitted by the [result schema](../../evaluation/google-sdp/result.schema.json); no raw or redacted fixture text is committed as a result artifact.

Google's [infoType documentation](https://docs.cloud.google.com/sensitive-data-protection/docs/concepts-infotypes) identifies `EMAIL_ADDRESS`, `PHONE_NUMBER` and `CREDIT_CARD_NUMBER` as generic detectors. This seed asserts required detection only for synthetic `EMAIL_ADDRESS` cases. Phone and payment-card accuracy remains observation-only because this Change Set does not create telephone or checksum-valid card values.

Live execution requires both `--live` and the exact `PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK=I_ACKNOWLEDGE_SYNTHETIC_ONLY_GOOGLE_SDP_EVALUATION` environment value, plus a separately supplied trusted project identity. Neither control is set in CI. The runner has no endpoint, region, credential or provider argument; the adapter remains fixed to `me-central2` and `dlp.me-central2.rep.googleapis.com`. Offline success proves only schema, sanitization and harness behavior. Even fake-client case passes cannot award **PASS FOR FURTHER BOUNDED INTEGRATION**, because the existing security, detection quality, operations and image gates remain unproven. A case failure yields **FAIL AND RETAIN PRESIDIO**; otherwise the runner records **INCONCLUSIVE — MORE EVIDENCE REQUIRED** for later review.

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

Only the reviewed, generated synthetic seed corpus may be committed to Git. Future live-execution inputs and provider outputs belong in an approved evaluation workspace and must never appear in logs, traces, exception messages, LiteLLM metadata, audit envelopes, Git, or shared reports. Before execution, approve the bounded live corpus, expected high-risk cases, scoring method, and operational thresholds. No gate below is currently passed.

| Gate | Required evidence for a future pass |
| --- | --- |
| Security | No raw mandatory high-risk test value remains in a successful redacted output or appears in telemetry; every validation or redaction failure causes zero LiteLLM requests; global/cross-region configuration is rejected; no static Google credential is required. |
| Detection quality | Record precision, recall, false negatives, and false positives separately for Arabic, English, mixed script, obfuscated text, OCR-corrupted synthetic text, and each identifier category. Require zero false negatives for mandatory high-risk cases in the approved bounded corpus. This does not establish real-world accuracy. |
| Operations | Measure latency, timeouts, failure rate, regional endpoint behavior, response-schema stability, request-size behavior, and estimated evaluation cost against limits approved before execution. Do not infer results from this plan. |
| Portability and rollback | Keep Google request/response types behind a provider-neutral redaction contract. Presidio remains installed and available as the rollback path until separate replacement approval. No automatic fallback within a request. |
| Image qualification | Before selection, require locked dependencies, the exact OCI digest, vulnerability scan, SBOM, provenance, signature or attestation, policy evaluation, and deployment with that same qualified digest. None are performed here. |

The intended future identity path is GKE Workload Identity → Google IAM → the regional SDP endpoint. Binding and IAM authorization are not implemented or authorized here. Static service-account keys, embedded credentials, Git-committed credentials, LiteLLM keys, and application-managed provider secrets are prohibited. A future adapter must fail closed on missing configuration, wrong region, invalid endpoint, authentication or authorization failure, service unavailability, malformed response, incomplete de-identification, or failed policy validation, always with zero LiteLLM requests.

## Decision record

After review, record exactly one outcome: **PASS FOR FURTHER BOUNDED INTEGRATION**, **FAIL AND RETAIN PRESIDIO**, or **INCONCLUSIVE — MORE EVIDENCE REQUIRED**. None authorizes automatic production cutover, Presidio deletion, customer-data processing, production deployment, or a compliance claim. A pass still requires a separate ADR and Change Set before Google SDP could become authoritative.

Separate Change Sets are required before IAM, GKE execution, a live API call, image qualification or a provider authority change. AWS and Azure candidates could reuse the same sanitized result contract through the neutral `RedactorClient` boundary; no such adapter is implemented here.
