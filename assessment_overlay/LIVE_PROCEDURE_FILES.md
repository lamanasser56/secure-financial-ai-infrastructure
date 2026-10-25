# Bounded live procedure file inventory (2026-10-25)

This inventory is the execution checklist. Platform source and the seven image
subjects are fixed at main `41ffbf2`; only assessment files may change.
Private generated manifests, credentials, kubeconfig, and raw case evidence
must stay outside Git. The five historical PASS cases are not in the run.

| Gate / phase | Required files and inputs | Produced private evidence |
| --- | --- | --- |
| Source and scope | `CLAUDE_HANDOFF_FINAL.md`, `assessment_overlay/live-case-verdicts-final.csv`, `assessment_overlay/platform-images.lock.json`, historical `plans/scope.json`, `plans/resource-plan.md`, `plans/cost-plan.json`, `plans/cleanup-runbook.md` | Fresh run ID, start/deadline, baseline inventory, cumulative cost basis |
| Immutable platform render | `platform/clouds/gke/render.py`, `platform/clouds/gke/kubernetes/**`, `platform/core/src/agent_platform/platform_secrets.py`, `platform/core/src/agent_platform/programs/{redactor_server,phone_guard,gateway_entry}.py`, all seven locked image references | Main render SHA, seven digest checks |
| Assessment transforms | `assessment_overlay/{render_live_bundle,patch_gateway_stub,provider_stub,patch_redactor_bundle,redactor_server,sdp_guard,seed_sdp,patch_ops_stub,ops_server_assessment,stage_live_bundle}.py` | Private 143-object bundle, seven ordered stages, source/route/stub hashes, generated synthetic Secrets |
| Offline tests | `assessment_overlay/{test_followup,test_live_tooling,container_startup_preflight,container_redactor_probe,container_ops_probe}.py`, `scripts/check.sh`, `scripts/lint-repository.sh`, `.github/workflows/ci.yml` | Test logs and image startup receipt from worker VM |
| Exact image and local gateway rehearsal | Worker Docker, digest-pinned App/Ops/Financial/Guide/Gateway/Database/Redactor, private stub source and route ConfigMap, local PostgreSQL, synthetic app/gateway/redactor Secrets | Exact image IDs, loopback-only gateway-to-stub D02 response, stub counter, network egress proof |
| Independent cleanup first | Historical `live-recovery-2026-10-24/{session,owned,janitor_core,janitor_daemon,operator_backup,deploy_janitor,rehearse_cleanup,qualification_finalizer}.py`, `janitor-startup.sh`; adapt to this fresh run and current $50 cumulative ceiling | Janitor and independent operator rehearsal, owned-resource ledger, takeover receipt |
| Disposable setup | Historical `live-recovery-2026-10-24/{resume_preflight,setup_owned,setup_runtime_identities,original_read_bindings,create_disposable_cluster,create_synthetic_secrets,prepare_admission,generate_apply_stages,apply_prerequisites_and_ops_binding}.py`; the new bundle/stager replace the old copied-source `prepare_assessment_bundle.py` and hardcoded `prepare_provider_stub.py` | Billing/API/IAM baselines, only four authorized original read/verify grants, one private cluster, staged apply and two seeded ledger readbacks |
| Release admission | Historical `live-recovery-2026-10-24/{qualify_images,verify_provenance,verify_image_signatures,prepare_release,setup_attestor,create_attestations,sign_images}.py` and pre-existing signed release evidence | Four published digest qualifications, retained service qualifications, attestations and Binary Authorization readback |
| Twelve cases | Historical `live-recovery-2026-10-24/{run_d02_sdp,run_d02_policy_phone,run_finance_live,run_boundary_probe,run_f1_live,run_f1_outage,run_f1_policy_fault,run_f2_worker_live,run_f4_approval,run_f4_replay_restart,verify_live_runtime}.py` plus fresh bounded probes for D04/D05/D06/D07/O03/O04/K01/K02/K03/K05/R01 | Before/after completed-redaction and SDK-attempt ledgers for every case; per-case verdict and scoped evidence |
| Cleanup and final reporting | Historical `live-recovery-2026-10-24/{independent_cleanup,qualification_finalizer,restore_final}.py`, fresh owned ledger, current `CLAUDE_HANDOFF_FINAL.md` and 40-case CSV | Full independent absence readback, four grant revocations, API/billing baseline restoration, TERMINATED worker, cost and verdict receipts |

Historical operator scripts are reference inputs only until copied, reviewed, and
adapted to the fresh run. In particular the historical bundle script replaces
platform source and is forbidden; the new assessment transform restores the
exact main redactor code after main's renderer accidentally substitutes the
`PROJECT_ID` substring inside `PORTFOLIO_PROJECT_ID`.

The case runner must stop on security failure, either durable ceiling, time
breach, or lost cleanup ability; isolated tooling failures become INCONCLUSIVE.
It must read both redactor ledgers immediately before and after each case.
