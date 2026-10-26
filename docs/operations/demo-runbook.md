# Release and recording runbook

Use the selected release and current code, not historical PR numbers or a previous attack pass count. Code/offline tests and builds run on the approved worker; use the cluster only for the final deployment and verification phase. Keep private project identities and unfiltered cloud output out of the recording.

## Release qualification

1. Freeze source **S** after the approved fixes and checks. Build every first-party image from **S** on `secure-infra-worker`.
2. Keep the existing vulnerability gate unchanged. Refresh each pinned base and fix every applicable available fix before the freeze. Stop on a gate failure or a fix that cannot be applied; add no exceptions. Record no-fix findings per image.
3. Verify cryptographic signatures, KMS attestations and source provenance for exact image subjects. A tag, receipt or workflow certificate alone is not checkout-source proof.
4. Promote digests in lock/evidence-only commit **R**. Deploy those same digests with staged `make up`; do not rebuild a different source during promotion.
5. Run `make demo-check`. Every required resource must actually be ready and match the selected render/digests/evidence. A down cluster or zero workers is not ready.
6. Run the approved full live assessment on those exact images in its disposable project, under the same 25 October rules and hard ceilings: janitor plus operator, synthetic data and zero external LLM calls. Complete cleanup and billing unlink; keep the original project and persistent VMs outside that cleanup.

No historical assessment automatically qualifies the new source. Deployment corrections such as node-local DNS egress and staged apply from PR #142 match the older bundle's corrections, but later source/images still need their own qualification.

## Prepare the recorded state

```bash
make demo-reset
make onboard-check F=docs/examples/rejected-agent/agent.yaml
make attack
```

Reset asks for confirmation and returns to the declared demo state, re-seeds only its owned synthetic data and warms the redactor. An incomplete step exits nonzero. The rejected onboarding example intentionally exits nonzero; record its actual reasons rather than treating the expected refusal as a failed platform control.

The attack suite requires the current architecture, real exercised attacks and positive controls, exact release/runner binding and owned-fixture cleanup. FAIL and NOT_EXERCISED are distinct; neither is a pass. Do not run this live during the code/offline-test themes. After the final approved live run, verify that Break it reads the newly mounted bound report.

## Open the screens

```bash
make port-forward
make agent-forward A=financial
make agent-forward A=platform-guide
```

Keep the forwards in separate terminals and use ports 8080, 8081 and 8082 on `127.0.0.1`. Check the owner approval passphrase privately before recording; do not rotate unrelated secrets to fix a passphrase mismatch.

## Walkthrough at 1440×900

- Map: three cells, provider/DLP connectors, allowed/denied paths, every explanation and the event strip. Show supported masking limits, not a promise to hide names/passports.
- Agents and Onboard: all passports, observation/inference/declaration/failure labels, review details, rejected example and supported Try/return links.
- Financial: English/Arabic sign-in, Ask suggestions from the declared demo period, response/refusal trace, Expenses, draft/navigation handling and confirmed sign-out. Use synthetic inputs only.
- Guide: English/Arabic questions, current corpus/source information, answer/refusal/loading/recovery and source details supported by the current UI.
- Ops: confirm zero false posture findings against the current inventory, scan details, every worker/core observation, owner-action explanations and the explicit approval/execution outcome. A fault/recovery demonstration is a deliberate final-phase mutation, never a code-test prerequisite.
- Break it: current bound attacks and positive controls, details and incomplete/failure states. Do not relabel unavailable results as historical success.

Capture each final screen at 1440×900 after the actual click-through. Synthetic browser-test screenshots are design/test evidence, not deployed screenshots. Preserve the exact source/digests and verification scope with the recording evidence.

When finished, stop the forwards. Scaling the platform down is a separate owner decision; no step here authorizes deletion of the retained engineering VMs or their disks.
