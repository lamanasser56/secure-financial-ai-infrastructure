# ServiceAccount and RBAC baseline

The namespace default ServiceAccount is hardened with `automountServiceAccountToken: false`. The reference trusted-runtime ServiceAccount also mounts no API token. LiteLLM and each Presidio component have dedicated ServiceAccounts in their own packages. None receives a RoleBinding or permission to read Secrets through the Kubernetes API; kubelet Secret delivery to an explicitly referenced Pod is a separate mechanism.

Grant a Role only after an actual workload declares an API need. The [read-only example](../examples/rbac-configmap-reader.example.yaml) shows narrow namespace/resource/name scoping and is excluded from the base. Product frontend and backend ServiceAccounts from MASAR are omitted.
