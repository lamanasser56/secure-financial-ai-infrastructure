# Google SDP qualification for the bounded agents

**Status, 2026-10-04: preparation only.** The owner stopped further Presidio
remediation and selected SDP replacement evaluation as the intended direction.
This plan authorizes no execution, cloud mutation, real-data processing, provider
cutover or deletion. Presidio remains authoritative; the private demo remains
offline. Preserve completed source, quarantined candidates and original evidence.

## Current preparation decision

The [exact coverage/provenance matrix](google-sdp-agent-coverage.md) records 42
safe **offline** cases and 45 unprepared cases in five required classes. The
87-case live campaign is **BLOCKED**, not replaced with a three-class campaign.
The [candidate checkpoint](google-sdp-agent-preparation-checkpoint.md) records
fresh artifact evidence and precise execution blockers. There is no execution
approval request while required provenance and detector configuration are absent.
The [consumer inventory](google-sdp-agent-integration-retirement.md) preserves
independent gateway/authentication gates and an ordered conditional retirement.

## Actual historical result

Agent preparation is preserved at `50240d04be9ae3337620b115df036d46ac851d89`.
The completed SDP run used infrastructure source
`5b47c1cb363e5adb346b116ec26c68cf8a1de208`, image-build source
`e5ddb647b67a877c2df8ea0b104bc3f0f28f1fd9` and signed registry manifest digest
`sha256:2b9a62198d52f843c3dd8f4393965855768c0c961f78d860d4c2a6b5d4339a8d`.
That signature does not sign later infrastructure/agent source or a new image.

The private evidence set `sdp-gke-contract-repair-5b47c1c` contains the actual
schema-validated `live-result.json`, SHA256
`d206c9564388b8a33219ccd9db3416deb68d42c73d5c40d21dece817cd0bd9f9`.
One committed nine-case Job produced **six PASS, zero FAIL, three INCONCLUSIVE**:
four email cases and two negative controls passed. Nine inspect and nine deidentify
SDK attempts exhausted the approved 18-attempt budget; application/Job retries were
zero. Attempts are not exact server receipts or billed operations.

| Inconclusive case | Actual observation | What qualification requires |
| --- | --- | --- |
| `observe-obfuscated-007` | Reserved-domain email with `[at]` and `[dot]`; no category detected | Make obfuscated email mandatory for the replacement profile and qualify reviewed transformations without unsafe normalization or relaxed scoring. |
| `observe-phone-008` | A sentence describing letters instead of digits; it contained no phone number | Reviewed safe test-number provenance, valid-format positives and matched negatives. This case did not measure phone accuracy. |
| `observe-card-009` | A sentence describing a placeholder without digits/checksum; it contained no card value | Documented non-production test-card values, checksum/format positives and negatives. This case did not measure card accuracy. |

The [seed harness](../../scripts/evaluate-google-sdp.py) always marks
`observation_only` cases INCONCLUSIVE, even if categories match. It never awards
replacement readiness. Category-set agreement does not establish span recall,
precision or absence of undetected leakage. Preserve these historical outcomes;
do not relabel them after changing a corpus or detector.

Recorded cleanup on 2026-10-03: creation apply began at 20:02:02 Asia/Riyadh,
cleanup began at 20:31:42, native absence verification finished at 20:59:27
(57.41 minutes). Workloads, cluster/pools, node VM/disks/MIGs, VPC/subnet,
router/NAT/address/firewalls and temporary node-system-role binding were verified
removed; node GSA was disabled. Retained private state, identities, signed image,
release configuration and evidence are outside this preparation's cleanup scope.
Storage/registry costs continue; bills are unreconciled. No historical cluster
four-/six-hour clock remains active. These are recorded facts, not a fresh cloud
inventory. Preserve the existing worker and offline UI.

## Required coverage and current gaps

Required classes come from the existing closed
[runtime contract](../../runtime/phase3/trusted_runtime.py); both agents must
preserve all eight and the pseudonymous tenant-reference invariant. The
[SDP adapter](../../runtime/phase3/google_sdp_adapter.py) currently maps only the
first three rows and is unwired from the authoritative agent composition.

| Neutral class | SDP candidate to qualify | Remaining requirement |
| --- | --- | --- |
| `EMAIL_ADDRESS` | `EMAIL_ADDRESS` plus reviewed obfuscation rule | All spans, repetition and English/Arabic/mixed contexts. |
| `PHONE_NUMBER` | `PHONE_NUMBER` | Safe test-number source, country/numeral/spacing variants and negatives. |
| `CREDIT_CARD` | `CREDIT_CARD_NUMBER` | Documented test values, checksum controls and exact neutral mapping. |
| `IBAN_CODE` | `IBAN_CODE` | Safe Saudi-format fixtures, independently checked format/checksum and representations. |
| `SAUDI_NATIONAL_ID` | Reviewed custom detector | Authoritative format, safe generation, distinction from resident IDs/ordinary numbers. |
| `SAUDI_RESIDENT_ID` | Reviewed custom detector | Authoritative format, safe generation and unambiguous mapping. |
| `SAUDI_VAT_ID` | Assess `VAT_NUMBER` plus reviewed custom detector | Generic availability does not establish Saudi coverage; verify format/context. |
| `SAUDI_BANK_ACCOUNT` | Assess `FINANCIAL_ACCOUNT_NUMBER` plus reviewed custom detector | Define supported account references without inventing a universal Saudi bank format; retain ordinary amounts/dates. |

Google's [detector reference](https://docs.cloud.google.com/sensitive-data-protection/docs/infotypes-reference)
lists the generic candidates. No dedicated Saudi detector was identified in the
reviewed list; this is an assessment limitation, not a live API support test.
The [custom regex mechanism](https://docs.cloud.google.com/sensitive-data-protection/docs/creating-custom-infotypes-regex)
supports reviewed patterns but supplies neither authoritative formats nor proof
of accuracy. Version allowed types, likelihood thresholds, rules, transformations
and mapping in trusted deployment configuration. No request may choose them.

Names, addresses, commercial-registration numbers, documents, images and actual
OCR are outside this eight-class profile. IP is a historical negative control,
not a required detector. Expanding required coverage needs a separate contract
decision; a limited pass cannot be presented as universal Presidio equivalence.

Infrastructure tools must continue reading only approved sanitized evidence;
this profile does not authorize raw CI logs, private keys or credentials as input.
Financial fixtures remain synthetic and server-scoped to the trusted tenant.

## One bounded qualification campaign

### A. Reversible preparation on secure-infra-worker

1. Review authoritative formats and synthetic-value provenance for every class.
   An invented plausible phone/account/ID is not proven safe by a `synthetic` label.
   Unresolved provenance blocks the live campaign; do not silently omit a class.
2. Prepare a separate versioned corpus/result schema with exact expected spans,
   categories, redact/retain/reject action, language and generation/review sources.
   Keep the original seed and actual result unchanged as historical evidence.
3. Prepare adapter changes separately from authority selection: closed eight-class
   mapping, UTF-8 input/output bounds, completeness/truncation checks, deterministic
   overlap handling, neutral sanitized failures and cumulative SDK budgets.
   Fake-client failures prove local containment, not real Google behavior.
4. Keep inspect/deidentify on one fixed regional client, retries disabled. Proposed
   per-RPC deadline: three seconds; overall redaction ceiling: eight seconds inside
   the unchanged agent ten-second limit. Measured feasibility is required; do not
   extend existing limits to accommodate service latency.
5. Qualify the changed image: locks, regression tests, reproducibility, fresh
   SBOM/Trivy/KEV evidence, unchanged vulnerability policy and redacted scans.
   Changed bytes require fresh provenance, not the old image's scan/signature.
   Do all dependencies/builds/tests on the worker; no laptop installation.

### B. Frozen proposed matrix

| New cases | Count | Scope |
| --- | ---: | --- |
| Mandatory single-class positives | 48 | Eight classes × three contexts (English/Arabic/mixed) × two reviewed representations; distribute formatting/repetition/punctuation variants. |
| Matched negatives | 24 | Eight classes × three contexts; invalid formats/checksums where applicable and ordinary business values. |
| Multiple identifiers | 6 | Two per context, with reviewed overlap behavior and all expected protected spans. |
| Representation stress | 9 | Three obfuscated-email, three Unicode/numeral and three OCR-like synthetic-text cases; mandatory redaction or explicit fail-closed rejection. |
| **Total** | **87** | At most one inspect and one deidentify invocation per case. |

Freeze exact inputs, spans, expected actions, thresholds and source/image hashes
before approval. This is a bounded sample, not exhaustive class/representation
coverage. The original nine cases are comparison evidence, not new calls.
Stop calls on a required failure; unexecuted cases remain UNKNOWN. Do not tune
against live results and rerun automatically.

Supported mandatory positives, including obfuscated email, must redact correctly;
refusal is not a detection pass. A declared unsupported representation may require
safe rejection, reported separately from recall and availability. Never count a
rejected input as a true-positive detection. Compare with preserved Presidio
evidence where valid; no new Presidio remediation or qualification attempt is
part of this campaign.

### C. Separate execution checkpoint; not authorized here

After offline gates pass, present one complete saved-plan/resource/IAM/API/network/
release/cleanup bundle. The exhausted 18-call approval does not cover this corpus,
image or agent integration. Proposed ceiling: **174 content SDK attempts plus
at most one separately approved `infoTypes.list` metadata attempt = 175 total**.
One Job only, zero SDK/application/Job retries. Verify metadata method/location
and permission before including it; invent no role or speculative grant. Inline
text configuration proposes no stored detector/template or cryptographic-key
resources. Exact values and saved plans are required before execution approval.

Keep trusted deployment `us-east1`, `dlp.us-east1.rep.googleapis.com` and parent
`projects/PROJECT_ID/locations/us-east1`, following Google's
[regional request contract](https://docs.cloud.google.com/sensitive-data-protection/docs/specifying-location).
Reverify availability and project authorization at the checkpoint. No request-selected
region, global fallback, real records/uploads or Saudi-residency claim.

If reusing temporary GKE, enumerate the exact current plan instead of assuming
the previous 24-resource bundle still matches. Keep dedicated namespace/KSA
`google-sdp-evaluation`, hardened Job, no ingress, digest/signature verification,
exact-source release trust and least privilege. A new release or source-SHA WIF
change needs explicit authorization; neither is implicitly approved by this plan.

Before unsuspending, specify and perform genuine zero-SDP-call native allow/deny
tests: approved DNS/metadata identity/regional HTTPS; reject other destinations,
ports and unauthorized namespace paths. Preserve application endpoint pinning.
DNS-derived IP/port policy does not establish Layer-7, shared-IP or DNS-query
isolation. Never broaden egress to pass a probe.

Proposed Job active deadline: 900 seconds, `backoffLimit: 0`. Reserve two attempts
before each case and count before dispatch; abort on exhaustion, timeout, malformed
output or required failure. Proposed cluster lifetime: two hours from first creation
apply; cleanup by minute 90 or immediately on failure, including partial resources.
Operator cleanup and owner takeover after disconnect remain necessary. Job TTL
does not delete a cluster. These are proposed limits, not automated guarantees.

Google's [content pricing](https://cloud.google.com/sensitive-data-protection/pricing)
uses bytes and a 1 KB minimum. Deidentify can also inspect; type replacement with
inspection is exempt from transformation-byte charges. Conservatively charge
174 requests at 4 KiB and USD 3/GiB inspection plus 87 at 4 KiB and USD 2/GiB
transformation: approximately USD 0.003, excluding infrastructure/traffic/logs/
storage. Do not assume available free tier. Reprice the exact plan and temporary
bootstrap before approval. Proposed incremental operator stop threshold: USD 5,
not a billing cap. Existing worker/MASAR and retained storage costs are separate.

## Every remaining acceptance gate

| Gate | Required evidence / current gap |
| --- | --- |
| Scope and safe corpus | All eight classes, authoritative formats, safe reviewed synthetic inputs, exact spans and supported representations frozen. Three classes have safe partial offline fixtures; five mappings/fixture sets and Saudi phone variants remain blocked. |
| Detection and preservation | Zero missed mandatory spans or protected-fragment leakage, including declared variants. TP/FP/FN and precision/recall per class/language with denominators. All mandatory negatives retain safe amounts, dates, evidence IDs and pseudonymous tenant references. Missing coverage is INCONCLUSIVE. |
| Complete responses | Candidate now rejects truncated/missing results, unknown types, invalid Unicode/UTF-8 offsets, duplicates/conflicting spans, malformed/oversized output and inconsistent transformations. Locked SDK/offline checks do not prove real response compatibility; returned-fragment checks cannot reveal undetected spans. |
| Fail closed | Auth/config/timeout/quota/provider/output/audit failure gives a fixed sanitized refusal, zero subsequent LiteLLM/tool activity, no raw/partial output or fallback. Distinguish offline injection from real service evidence. |
| Neutral runtime contracts | Preserve `RedactorClient`/`RedactionResult` and closed categories. Review migration of Presidio-specific trace/error labels and schemas; never label Google calls as Presidio. Leave current authority factories unchanged until separately approved integration. |
| Deadlines and sizes | Candidate now uses three-second RPC deadlines capped by the remaining eight-second monotonic budget, replacing incompatible historical 20-second deadlines; UTF-8 bounds and offline timeout tests are prepared. Real latency/availability within existing ten-second redaction and conversation bounds remains unproven. |
| Agent amplification | Count redactions of user input, context, assembled prompts, tools and final answers; global SDK/cost budget independent of resets. Four model calls do not imply eight SDP calls. Cancellation does not undo a remote accepted operation. |
| Privacy/location | Google receives original text before redaction. Review processor/data-egress, retention, region and allowed classes before real data. Synthetic US tests establish neither Saudi residency nor production/privacy approval. |
| Identity and network | Reverify exact keyless binding, least privilege, no static credentials, TLS, private boundaries and genuine native allow/deny evidence. Historical nine-case authentication does not qualify a new topology or agent identity. |
| Supply chain and provenance | Fresh locks/behavior/reproducible image/SBOM/scan/policy; exact registry digest/signature. Keep image and infrastructure sources distinct. No silent image/provider upgrade or vulnerability exception. |
| Audit and secrets | Versioned sanitized events, no raw spans/transcripts/provider errors/credentials in logs/downloads, bounded private retention and durable fail-closed delivery. Scans do not prove universal secrecy. |
| Other live-agent services | Qualified LiteLLM image, scoped expiring client keys, gateway-only provider identity, real authentication/tenant authorization, model entitlement/tool/Arabic response behavior, budgets and durable audit. An SDP pass does not pass these separate blockers. |
| Operations and cleanup | Attempts versus receipts/bills, fresh quota/cost checks, hard dispatch budget, no retries, partial-provision cleanup, native deletion and retained inventory. A future run needs its own verified finish. |
| Review and drift | Reviewed evidence decision, configuration/version expiry and requalification triggers. Managed detector behavior can change. Owner self-review is not independent review; no automatic rerun. |

Google's [inspection result contract](https://docs.cloud.google.com/sensitive-data-protection/docs/reference/rest/v2/InspectResult)
exposes truncation; a truncated response is an arbitrary subset. Returned finding
counts cannot establish complete redaction.

## Conditional integration and Presidio retirement

1. **Evidence decision:** FAIL, INCONCLUSIVE or PASS FOR FURTHER BOUNDED INTEGRATION
   for the frozen profile. Resolving only three seed observations is insufficient;
   a pass authorizes neither production nor cutover.
2. **Offline integration after reviewed ADR:** prepare trusted startup provider
   selection behind the neutral boundary, honestly migrate stage/error/audit
   contracts and test both agents/bilingual answers/tenant/tool isolation/results/
   timing/multiplied budgets with fakes. Keep SDP disabled and Presidio source.
3. **Conditional synthetic agent execution:** after SDP and independent gateway/
   identity/image/audit gates pass, present one exact follow-up execution bundle.
   Model traffic stays exclusively through LiteLLM with a scoped client key;
   no master key or direct model-provider SDK in either agent.
4. **Explicit authority approval:** separately approve a scoped switch after
   evidence/privacy/operations review. Trusted configuration selects one provider;
   unavailable SDP refuses without fallback. Simulated UI stays labelled offline.
5. **Separately reviewed retirement:** inventory factories, locks, schemas,
   manifests, policies, CI/tests, runbooks and consumers. Remove obsolete active
   dependencies/resources only after verified migration, retaining sanitized
   historical attribution/evidence. Do not delete Presidio now. A rollback image
   must pass policy; the vulnerable candidate is not a live rollback. If none is
   qualified, disable live agents and retain the offline demo.

Preserve historical UNKNOWNs: unavailable state-read/Data Access history,
unscanned historical state versions, incomplete IAM deltas, transitive impersonation/
signed-URL/worker credential assessment, independent review, project-pool isolation
and Layer-7/shared-IP/DNS-query containment. The bootstrap node's runtime version
was not captured. Broader accuracy, exact billed operations/cost, production
authorization and full CS6 remain unproven.
