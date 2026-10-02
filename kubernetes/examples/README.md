# Integration examples

These are deliberately excluded from `kubernetes/base`. They show separable migration credentials, minimal API RBAC, isolated backup storage, and CSI storage choices without including product code, live credentials, image identity or cluster-specific addresses. Resolve placeholders, qualify images, confirm ownership and test the target environment before any deployment.

The [migration Job](migration-job.example.yaml) uses its own Secret and ServiceAccount, never a runtime credential. The [backup example](backup-cronjob.example.yaml) writes a dump to a separate PVC but does not establish an off-cluster recovery copy. [Storage examples](storage-classes.example.yaml) require an approved CSI driver. The [RBAC example](rbac-configmap-reader.example.yaml) is an optional narrow permission pattern, not a permission granted by the base.
