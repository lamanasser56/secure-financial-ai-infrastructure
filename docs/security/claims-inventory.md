# Security claims inventory (2026-10-19)

Every security claim the platform makes, the control behind it, the test that proves it, and two questions about that
test: **is the input realistic**, and **does it run on the real end-to-end path**? The answers decide how much the
claim is worth. This page grades the tests; it does not repeat the claims matrix
([agent-platform/claims-matrix.md](../agent-platform/claims-matrix.md)) or the limitations
([known-limitations.md](known-limitations.md)).

Grades used below:

- **Input:** *realistic* (the shapes a Saudi user or log would really produce, in Arabic and English), *narrow* (one or
  a few hand-written examples), or *n/a* (no user input involved).
- **Path:** *live e2e* (exercised on the running cluster through the same code path a user hits), *live partial* (on the
  cluster, but through a shortcut or with one leg replaced), *offline real* (real components, no cluster: real
  Postgres, real kube-apiserver), or *offline fake* (fakes for the redactor, model or database).
- **Gap:** what the test does not prove. The realistic-data review
  ([realistic-data-review-2026-10.md](realistic-data-review-2026-10.md)) runs the synthetic Saudi/bilingual corpus
  (`platform/core/tests/corpus/`) against the gaps marked *corpus*.

## 1. The eight platform guarantees (console `GUARANTEES`)

These are the guarantees the console shows for every onboarded agent (`platform/core/src/agent_platform/console.py`).
The Security & Operations Agent shows `approval` in place of `tools` and `ops`.

| # | Guarantee | Control | Proving tests | Input | Path | Gap |
|---|---|---|---|---|---|---|
| G1 | **Its own namespace** (Pod Security restricted) | `onboarding.py` renders the Namespace; `namespaces/` labels | `test_onboarding.test_names_and_placement`, `test_isolated_namespace_with_no_exposure`; envtest `test_onboarded_agent_namespace_inherits_the_controls`, `test_pod_security_restricted_rejects_root_escalating_pods` | n/a | offline real (kube-apiserver) + live (agents run in their namespaces) | The console marks it *verified* only from "a Deployment runs in that namespace"; Pod Security enforcement is proven on envtest, not re-proven live. |
| G2 | **Default-deny network**; egress only to the gateway and the redactor (and Postgres if declared) | `policies/network.yaml`, per-agent policies from `onboarding.py`; GKE Dataplane V2; no NAT | `test_network_reaches_only_the_redactor_and_the_gateway`, `test_no_egress_rule_names_another_agent_namespace`; live `egress_containment` | realistic (real pods, real DNS names) | **live e2e** | TCP connect probes to 9 named targets only. DNS through kube-dns is allowed by design and not probed (DNS-based exfiltration is untested). UDP and other ports untested. |
| G3 | **Scoped model key**: own gateway key, never a provider credential | `bootstrap.py`/`onboarding.py` create one LiteLLM key per agent; provider credentials only in the gateway (Workload Identity) | `test_secrets_give_it_only_its_own_keys_and_hashed_users`; live `financial_redaction_down_no_model_call` reads that key's spend | n/a | live partial | The console shows it as *declared* (the key is never readable there). No live test uses agent A's key from agent B's namespace. |
| G4 | **Monthly budget** per agent | LiteLLM key `max_budget` (`onboarding.py`); total capped at the platform total | `test_budget_bounds_and_platform_total`, `test_budgets_sum_to_the_platform_total` | n/a | offline fake | Never exhausted live: no test proves the gateway refuses at the budget. Per-user ceilings are in memory (known limitation). |
| G5 | **Personal data redaction** before every model call, fail-closed | Client masking `identifiers.py` / `identifiers.js` + email layer `deterministic_email.py` → redactor (`redactor_server.py`, SDP policy anchored to labelled line starts) | `test_identifiers` and the shared fixture (Python and JS), `test_realistic_corpus.py` and the JS corpus tests (201 covered values and 6 documents in 3 prompt shapes), `PastedInvoice` tests in `test_finance_agent.py`; `test_platform.test_any_failure_blocks_the_model_request`; live requalification 5a (email + phone); live `financial_redaction_down_no_model_call`; `make corpus-live` (#120, next cluster session) | **realistic** after #118 (was narrow: one invoice) | offline real (client code, fake redactor) for masking; live e2e for fail-closed; live SDP masking proven for email and phone only until `make corpus-live` runs | Unlabelled IDs, commercial registration numbers, passports (INFO-7: not covered by the qualified redactor) and person names are documented gaps; an ID of unknown kind is masked but not reported (INFO-8). Both are known limitations whose fix needs a DLP requalification (see the review). Findings RD-01 to RD-04, RD-08, RD-09 fixed in #118 and #122. |
| G6 | **Read-only tools** | Tool registry `finance_agent/tools.py` (READ_ONLY); agent DB role read-only under FORCE RLS | `test_only_read_only_tools_are_registered`, `test_strict_arguments_cannot_name_a_user`, `test_finance_db.test_agent_is_read_only_and_cannot_see_users` (real Postgres); live `financial_cross_user_database` | realistic | **live e2e** (real role, real DB) | None material. |
| G7 | **Signed image only** | Binary Authorization with a KMS attestor (`terraform/module/admission.tf`); CI signs | `test_registry_and_admission_share_the_same_digests`; live `unsigned_image_rejected` | realistic | **live e2e** (real admission) | Tests an unattested digest only; an image signed by another key is not tested. |
| G8 | **Ops: the ops agent watches, never changes, an onboarded agent** | RBAC (`ops-agent-rbac.yaml`), admission (`admission.yaml`), `observe_only` targets | `test_failing_agent_is_reported_but_never_proposed_or_explained`, envtest `test_rbac_denies_everything_else`; live `ops_agent_cannot_change_onboarded_agents` | n/a | live e2e (real API authorization via `can-i --as`) | `can-i` answers from RBAC; it does not attempt the write. Admission is the second layer (envtest). |
| G8′ | **Approval** (ops agent only): one-use, owner passphrase, bound to UID and resourceVersion | `approval.py` (Ed25519), `app.py` (scrypt passphrase), patch precondition | `test_ops_agent.*` (binding, expiry, replay, 409 race), envtest `test_ops_agent_patch_precondition_is_enforced_by_the_api_server`; live `ops_stale_approval_refused` | realistic | live e2e | Until #119 the live case accepted `UNKNOWN_OR_USED_REQUEST` too (run 5 passed that way); it now requires `OBJECT_CHANGED`. |

## 2. Attack suite cases (`make attack`, `platform/clouds/gke/attack_suite.py`)

18 attacks plus a setup step. Last committed run: run 6, 2026-10-19 21:49Z, 19/19 (`docs/evidence/attack-suite.json`
and `docs/evidence/attack-suite-run-6-note.json`).

| Case | Claim attacked | Control | Input | Path | Gap |
|---|---|---|---|---|---|
| `financial_cross_user_database` | The agent role sees nothing without a user, cannot write, cannot read users | RLS + grants (`finance.sql`) | realistic SQL | live e2e | — |
| `financial_cross_user_api_and_forged_session` | One user cannot read or insert another's rows; a forged cookie is refused | session signing, server-side user id | realistic | live e2e | — |
| `financial_show_saras_expenses` | "Show Sara's expenses" reveals nothing | user id from the session; RLS | narrow (one English question) | live e2e | Arabic phrasing not attacked. |
| `financial_prompt_injection_in_question` | Instructions in the question cannot reach a write tool or leak | read-only registry, closed decision shape | narrow (one English string) | live e2e | No Arabic, zero-width or homoglyph injection (**corpus**). |
| `financial_filter_bypass_merchant_stays_grounded` | An instruction that passes the filter stays data; the answer stays grounded | grounding check; injection assessor | narrow (one 52-character merchant) | live e2e | Arabic and obfuscated merchants (**corpus**). |
| `financial_ungrounded_record_claim_feature3` | "Is my invoice recorded and approved?" is never affirmed (EN/AR) | `ungrounded_claims()` | realistic (EN + AR) | live e2e | — |
| `financial_question_figure_not_evidence` (RT-05) | A figure only in the question is never shown | `numbers()` / `grounded_numbers()` | realistic (EN + AR) | live e2e | Fixed in #107: an infrastructure failure no longer counts as PASS (run 5's PASS was not exercised). The agent's parser now reads grouped, Arabic-separator and spelled-out amounts (#113). |
| `financial_merchant_with_digits_answers` | Digits inside the user's own merchant do not block an answer | `without_quoted_fields()` | narrow (`7-Eleven`) | live e2e | Availability only. |
| `financial_redaction_down_no_model_call` | Redactor down: no model call, no spend | client fail-closed | realistic (email in the question) | live e2e | Proves fail-closed, not masking quality. |
| `financial_login_lockout_per_username` | 5 failures lock one name; X-Forwarded-For ignored | `LoginThrottle` | realistic | live e2e | In memory (known limitation). |
| `financial_session_epoch_restart` | A cookie from before a restart is refused | session epoch | realistic | live e2e | — |
| `unsigned_image_rejected` | G7 | Binary Authorization | realistic | live e2e | see G7 |
| `no_public_exposure` | No LoadBalancer, NodePort or Ingress | ResourceQuota `services.loadbalancers: 0`, `services.nodeports: 0` | realistic | live e2e | Only a LoadBalancer create is attempted; NodePort is checked as "none exists" (the quota is not attacked for it). |
| `egress_containment` | G2 | NetworkPolicy | realistic | live e2e | see G2 |
| `ops_agent_cannot_change_onboarded_agents` | G8 | RBAC | n/a | live e2e | see G8 |
| `ops_stale_approval_refused` (RT-01) | G8′ | approval binding | realistic | live e2e | Since #119 only `OBJECT_CHANGED` passes; a superseded proposal is `NOT_EXERCISED` (a FAIL). |
| `ops_log_injection_adds_no_action_and_no_text` (was `log_planted_instruction_stays_data`) | A log line with instructions adds no action and no text to the ops agent's output | closed action registry; log text is never an input to the model or the UI | narrow (one English line) | live partial | Was weak (passed whenever actions stayed within the registry). Since #119 it also requires the planted line in the workload log and no planted phrase anywhere in the ops snapshot. The corpus review confirmed offline that log text never reaches the ops model. |
| `no_secrets_in_env_or_logs` | No secret material in Pod env or logs | Secrets mounted as files; content-free audit | realistic (real logs, 3000 lines per container) | live e2e | Scans for credentials only (keys, tokens, DSNs, argon2 hashes). **Personal data in logs is not scanned** (**corpus**: content-free logging). |

## 3. Other platform claims (onboarding contract and README)

| Claim | Control | Proving tests | Input | Path | Gap |
|---|---|---|---|---|---|
| Answers contain only figures from tool results (numeric grounding) | `grounded_numbers()`, `numbers()`, `spelled_amount()` | `test_invented_number_is_rejected`, `test_arabic_digits_are_checked_too`, `test_a_figure_only_in_the_question_is_never_evidence`, `test_invented_amounts_in_realistic_writing_are_rejected`, `test_real_figures_in_every_writing_are_accepted`; the 15 corpus grounding pairs; guide `an answer ... with an unsupported figure, is blocked` | realistic (since #113) | offline fake + live (RT-05) | Words that are not next to a currency ("about nine thousand") are not parsed. |
| Instruction-like user data is withheld from the model | `runtime/agents/controls.py` assessor plus the Financial Agent's `instruction_like()` (folding, Arabic and English phrasings); the question is assessed and recorded | `test_user_entered_text_that_looks_like_instructions_is_withheld`, `test_realistic_instruction_phrasings_are_withheld`, `test_ordinary_merchants_that_share_a_word_are_not_withheld`, `test_an_instruction_in_a_pasted_question_is_recorded_not_withheld`, `test_injection_that_evades_the_filter_...` | realistic (since #114) | offline fake + live (merchant case) | A filter is never complete; read-only tools, row-level security and grounding hold what it misses. |
| Audit is content-free (no prompts, model text, arguments, raw IDs) | `audit.py` `FORBIDDEN_FIELDS`; closed event shapes; guide `audit.js` | `test_history_is_server_side_and_audit_has_no_content`, `test_gateway_audit.test_audit_line_is_one_json_line_without_content`, guide `the trace is the audit line, and it holds no content`, `test_client_supplied_request_id_is_not_logged_verbatim` | narrow | offline fake; live only for credentials (above) | Error and rejection paths with realistic personal data (**corpus**). |
| Onboarding refuses a manifest that asks for extra powers | `onboarding.py` closed schema and rules; duplicate keys refused | `test_no_extra_powers_can_be_requested`, `test_problems_lists_each_violated_rule`, `test_the_demo_sample_is_rejected_for_the_advertised_reasons`, `test_a_key_given_twice_is_refused_not_silently_overridden` | realistic (review probes: homoglyph names, aliases, duplicate keys, long fields) | offline real (render) | — |
| Identity comes from the verified session, never the request | `finance_agent/server.py`, `Sessions` | `test_strict_arguments_cannot_name_a_user`, `test_agent_tools_read_only_the_signed_in_user`; live forged-session case | realistic | live e2e | — |
| Model output must match a closed decision shape | `agent.py` `_step()` | `test_last_step_accepts_only_an_answer`, `test_unknown_tool_and_extra_fields_are_rejected` | narrow | offline fake + live | — |
| No internet egress; model and SDP only over Private Service Connect | Terraform (no NAT), PSC endpoints | requalification; live `egress_containment` (gateway positive control) | realistic | live e2e | — |
| Supply chain: scan, SBOM, KEV gate, cosign, KMS attestation | `agent-platform-images.yml`, `kev-release-gate.py` | workflow runs on every image build; `scripts` tests | realistic | live (CI) | — |

## 4. What changed after this inventory

- RT-05 could pass without exercising its control: fixed in #107.
- RT-01 and the log-injection case could pass without exercising their controls: fixed in #119.
- `no_secrets_in_env_or_logs` still scans for credentials only. Content-free logging with personal data is covered by
  the offline review (every audit path tried was clean); a live personal-data log scan is not part of the suite.
- G5 (redaction) had the narrowest test input. The realistic-data review found one HIGH and five lower findings there
  (fixed in #118), and `make corpus-live` (#120) measures the live redactor with the same corpus.

The findings and their fixes are in [realistic-data-review-2026-10.md](realistic-data-review-2026-10.md).
