# Backup and restore design

Recovery ownership, RPO, RTO, scope, retention and destination must be approved before selecting a schedule. An authorized cluster owner must first identify the effective control-plane datastore and its supported backup and restore procedure. A k3s installation does not by itself establish the datastore, snapshots or an off-node copy.

Protect independently: control-plane state, configuration and certificates; workload desired state and provenance; persistent data; PostgreSQL schema, roles and data; object references; audit evidence; and keys needed for restoration. Separate backup delete rights from routine workload access. Require encryption, integrity verification, retention, capacity monitoring and an isolated restore drill.

The [backup CronJob example](../../kubernetes/examples/backup-cronjob.example.yaml) is a synthetic pattern, not a production backup. A PVC in the same failure domain is not a disaster-recovery destination. A successful dump alone does not prove restore, RLS behavior, application consistency or recovery objectives.
