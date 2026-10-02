# Key and credential ownership

Keep four boundaries separate: gateway client authentication, cloud provider workload identity, database runtime/migration credentials, and artifact signing identity. The gateway administrative master key belongs only to LiteLLM. Product callers need separately approved scoped credentials; they never receive cloud provider credentials or the administrative key.

The target operator owns creation, storage, rotation, revocation, emergency access and recovery of each value. A Secret reference is a delivery mechanism, not evidence of encryption-at-rest, rotation or least privilege. The [non-deployable Secret example](../../kubernetes/secret-templates/litellm-master-key.secret.example.yaml) records only the required key name.

No KMS provider, Secret controller or production key is selected by this repository. Confirm cloud IAM, Kubernetes RBAC, node access, backup copies, audit logs and deletion behavior before activation.
