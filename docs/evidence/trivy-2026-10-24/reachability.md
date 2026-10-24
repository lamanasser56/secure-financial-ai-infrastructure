# App/Ops filelock exception: static reachability and raw scan evidence

Approval: owner-approved on 2026-10-25 for `CVE-2026-112940` / `filelock==3.32.7` / HIGH in App and Ops only, through 2026-11-06. This is a temporary local mitigation, not a claim that the finding is fixed or live-qualified. The [reviewed register](../../../policy/reviewed-image-exceptions.json) has one entry for each image. The gate verifies the exact image, Trivy target, advisory, package, installed and fixed versions, severity, and expiry. It checks the complete raw report against a fresh CISA KEV catalog before removing the single reviewed finding from the copy sent to the existing digest-pinned release gate. Financial and Guide have no exception. After 2026-11-06, a continuing finding blocks automatically.

## Reachability

The [GitHub advisory](https://github.com/tox-dev/filelock/security/advisories/GHSA-v4x8-3wr5-3wq8) identifies `ReadWriteLock` / `AsyncReadWriteLock` as the affected API, with exploitation requiring another local user able to manipulate the lock database directory. App starts `agent_platform.app`; Ops starts `agent_platform.ops.server`. Neither entrypoint nor repository runtime code imports `filelock` or the affected API. Static inspection of the installed dependency tree found `huggingface_hub.utils._shared_blobs` and `_fixes` import `FileLock`, `SoftFileLock`, `BaseFileLock`, and `Timeout`; `litellm.proxy.client.cli.commands.claude_settings` imports `FileLock`. No `ReadWriteLock` or `AsyncReadWriteLock` reference was found in those package trees. App and Ops inherit the same hash-locked dependency set, which explains the finding in both images.

Both deployment manifests run uid 65532 with `readOnlyRootFilesystem: true` and a private memory-backed `/tmp` (`platform/core/kubernetes/apps/workloads.yaml`, `platform/core/kubernetes/ops/workloads.yaml`). These controls reduce the advisory's local-user precondition but do not prove impossibility in every deployment. No live platform run was performed for this exception.

The fixed `filelock` version is 4.2.1. Current and newer inspected LiteLLM releases constrain `filelock` to `<4.0,>=3.16.1`, so installing 4.2.1 would violate the parent dependency. No forced install or hash-lock bypass was used. Reassess the parent dependency and remove both entries by the expiry date.

## Full raw Trivy reports

Each file is an unmodified JSON output from pinned Trivy 0.72.0 on linux/amd64. “Before” is main `3223c82`; “after” is branch `fix-app-ops-trivy-20261024` with the PyJWT, OpenTelemetry API, and base-image fixes but before this exception. All four still report one HIGH finding: `filelock 3.32.7 / CVE-2026-112940`, fixed in 4.2.1. Other reported findings are below HIGH and were not KEV matches against the catalog used for the offline gate. The workflow will retain its own raw post-push reports as CI artifacts.

| Image | Report | SHA-256 |
| --- | --- | --- |
| App, before | [app-before.json](app-before.json) | `96b3d5a3fd7acf34fc4302df399a9b6934344611b73ff7d085c21658e2ee7899` |
| Ops, before | [ops-before.json](ops-before.json) | `dfa8f1cd707a184ae276e46e56a936064250fdad948bc0627f23e21df884cfd7` |
| App, after | [app-after.json](app-after.json) | `e488731c72ca95a112fc558cd9c11b2a146ae0781104df4dcc970703af60d386` |
| Ops, after | [ops-after.json](ops-after.json) | `3a6c8f66e69bd35855419f0d830ed1d65635cf71f240a6031f59312b3728e871` |
