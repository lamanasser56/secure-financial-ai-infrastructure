# View the current platform

The GKE workload platform has no public application endpoint. Use the supported local forwards from the approved operator environment after deploying the selected release. Use `127.0.0.1`, not `localhost`, because Host/Origin checks accept the declared address.

| Forward | Address | Screen |
| --- | --- | --- |
| `make port-forward` | `http://127.0.0.1:8080/` | Map, Agents, Onboard, Ops and Break it |
| `make agent-forward A=financial` | `http://127.0.0.1:8081/` | Trusted Financial sign-in, Ask and Expenses |
| `make agent-forward A=platform-guide` | `http://127.0.0.1:8082/` | Guide using its bundled current documentation corpus |

Each forward stays open in its own terminal. A Try link navigates to the corresponding local service; it does not create or deploy that agent. Return links open the matching Console passport.

## Read the screen honestly

- The connection badge reports the last API outcome and browser receipt time. An old response is not an inferred outage; “API answered” does not certify every service or data freshness.
- Passports distinguish observed, inferred, declared and failing checks. Partial observation is not an overall VERIFIED result.
- Map groups three platform cells with **Audit · request events** underneath. Open details for the actual components, supported masking types and limits. Person names and passport numbers are not masked.
- Onboard is a read-only review. Its manifest table is a summary; the owner workflow performs validation/generation.
- Ops shows scan source/window/completeness separately from incident denials. Zero current findings requires a complete fresh scan; it is not a full assessment.
- Financial shows worker-reported steps and honest cost availability. Conversation/drafts survive page tab/language changes in memory; they are not stored durably in the browser.
- Break it shows a mounted report bound to its selected release and runner source. Missing/unqualified/historical results are not a fresh live pass.

Skip to content focuses the current main region without changing its route. Escape closes an explanation and restores its opener. The Console is English; Financial supports English/Arabic. Guide language and source presentation follow its current component behaviour and tests.

## Approve an action

Read the target, action and proposal age. **Approve & execute** performs the signed approval and execution flow. It is not an approval-only draft. A refused, expired or unknown response must not be labelled verified. A lost execution response is an unknown outcome; inspect current state before retrying. Read-only targets offer owner action rather than mutation.

Stop forwards when finished. `make down` snapshots/scales the declared platform; it does not delete the persistent engineering VMs. See the [runbook](operations/demo-runbook.md) and [retention policy](agent-platform/teardown-plan.md).
