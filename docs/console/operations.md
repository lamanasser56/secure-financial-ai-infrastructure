# Console Operations

The Ops screen reads current workload observations and posture through the trusted console front door.
It does not treat a count of operation denials as a security-posture result.

## Observations and scan scope

Workload counts come from `ops-agent /v1/snapshot`; expected Financial worker names and replica counts come from
the selected release inventory. All expected workers must have recent observations and meet their required counts
for the logical agent to appear healthy. Missing, old or scaled-down workers cannot be replaced by one healthy
worker. The compact workload table opens its returned facts on click. Declared core targets remain visible as **not observed** if no recent scan exists. The Ops API answering
does not prove its own pod digest or readiness independently.

The core target registry in `platform/core/kubernetes/ops/workloads.yaml` declares both mutable targets
(`min`, `max`, `health`) and read-only targets (`observe: read-only`). Gateway boundary, data broker and approval
executor are observed read-only. A target cannot mix those declarations. An observation entry grants no proposal
or execution authority. RBAC is generated from the single authority inventory in
`platform/core/src/agent_platform/ops/authority.json`; no secret-reading or mutation right is added to Ops.

The separate **Security posture** panel uses `ops-agent /v1/posture`. Its source, completed-check time and namespace
count are visible; Scan details explains scope and returned findings. The scan reads default-deny policy presence,
pod non-root flags, exact declared RBAC and image-rejection events. It is not a full security assessment.

Every failed resource list marks the whole scan incomplete, even if that namespace's policy list was readable.
Readable network facts remain available independently. Zero findings is a current verdict only when the scan is
complete, its declared namespaces have policy results, and the entire scan window is recent. The server publishes
the freshness contract from `agent_platform.observations`; the UI has no separate duration. Missing timestamps,
missing freshness metadata, reversed windows, stale scans and unavailable APIs cannot produce a current clean
verdict. An unavailable scan may show the previous result explicitly as historical context.

## Owner action

Each proposal shows its target, action, finding and age. **Approve & execute** requests both steps: it checks the
owner passphrase, then sends exactly that approval reference for execution. It does not merely save a pending
approval. The separate executor verifies the signature, bound action/evidence, expiry and one-use nonce; existing
RBAC and admission bounds remain in force. Ops itself has no mutation authority.

The browser clears the passphrase on submission, suppresses duplicate requests and preserves the final result
across observation refreshes and navigation. Refreshing observations preserves a draft passphrase for an unchanged
proposal; a changed or removed proposal does not inherit it. An expired proposal cannot be submitted.

Bootstrap and JSON failures have a visible unavailable state and a refresh path. A refused approval does not
request execution; a CSRF rejection requires a new bootstrap and an explicit retry. A lost execution response is
an **unknown outcome**, not proof that no change occurred. The UI never automatically replays that action.
`VERIFIED` describes the executor's checks for that particular change; `NOT_VERIFIED` does not imply the mutation
was absent. The last action remains separate from the current pending list.

Incident explanations are untrusted model text for display only. They cannot create an action or change an
approval. Read-only targets instead report the appropriate owner action; they do not trigger remediation or model
explanations.
