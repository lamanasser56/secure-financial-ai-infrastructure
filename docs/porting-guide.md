# Porting guide: GKE → EKS / AKS

**Status: documented, not tested.** Only the GKE implementation (`platform/clouds/gke`) was built and run live.
This guide maps each GKE dependency to its usual equivalent so an `eks/` or `aks/` module can be added behind the
same contracts. No EKS or AKS code exists in this repository.

## What is portable as-is (`platform/core`)

- **Kubernetes base** (`platform/core/kubernetes`):
  - namespaces with Pod Security "restricted"
  - default-deny NetworkPolicies and explicit allow paths
  - quotas and limits
  - the ops agent RBAC and its ValidatingAdmissionPolicy (built into Kubernetes ≥ 1.30)
  - the workloads
- **Application code** (`platform/core/src/agent_platform`):
  - the agents
  - `RedactorClient` (fail-closed)
  - one-use Ed25519 approvals
  - the Kubernetes client (in-cluster, stdlib)
  - Postgres RLS (`platform/core/database`)
- **Providers** (`providers/*.yaml`): LiteLLM profiles behind the stable alias `secure-financial-chat`.

## Cloud module contract
A cloud module (`platform/clouds/<cloud>`) must provide:

| Contract item | GKE implementation |
|---|---|
| A private cluster reachable only by an authenticated operator (no public LB/Ingress) | private nodes, private endpoint + IAM-only DNS endpoint |
| An L3/L4 NetworkPolicy CNI + an FQDN egress mechanism for the provider endpoint | Dataplane V2 + `FQDNNetworkPolicy` |
| Workload identity for exactly two KSAs (`platform/gateway`, `platform/redactor`) | GKE Workload Identity (KSA annotation) |
| A Retain storage class for Postgres + disk snapshots | `pd.csi.storage.gke.io`, `reclaimPolicy: Retain`, `gcloud compute disks snapshot` |
| Admission that rejects unsigned/unattested images | Binary Authorization (KMS PKIX attestor) |
| Metrics + an audit log destination for `audit_event` JSON lines | Managed Prometheus + Cloud Logging sink (30-day bucket) |
| Outputs for the overlay renderer | project/account IDs, control-plane CIDR, workload-identity principals, image digests |

## Mapping
| Concern | GKE (implemented) | EKS (documented) | AKS (documented) |
|---|---|---|---|
| Workload identity | Workload Identity Federation for GKE (`iam.gke.io/gcp-service-account`) | IRSA or EKS Pod Identity (`eks.amazonaws.com/role-arn`) | Microsoft Entra Workload ID (`azure.workload.identity/client-id`) |
| Image admission | Binary Authorization + KMS attestor | Sigstore policy-controller (or Kyverno verifyImages) with cosign keyless identity | Sigstore policy-controller / Ratify + Azure Policy |
| Signing key custody | Cloud KMS asymmetric key (owner-held) | AWS KMS key for cosign, or keyless only | Azure Key Vault key, or keyless only |
| FQDN egress | `FQDNNetworkPolicy` (Dataplane V2) | Cilium FQDN policy or an egress proxy; VPC endpoints for AWS APIs | Azure Firewall FQDN rules / Cilium (Azure CNI powered by Cilium) |
| Private Google API access | Private Google Access | VPC interface endpoints (PrivateLink) | Private Endpoints / Service Endpoints |
| No node internet egress | no Cloud NAT | no NAT gateway; endpoints only | no NAT / firewall default deny |
| Metrics | Managed Prometheus | Amazon Managed Service for Prometheus / self-managed Prometheus | Azure Monitor managed Prometheus |
| Audit log sink | Cloud Logging bucket + sink | CloudWatch Logs (Fluent Bit) | Azure Monitor Logs (Container Insights) |
| Operator access | `kubectl port-forward` via IAM DNS endpoint | private API endpoint + SSM/VPN, then `kubectl port-forward` | private cluster + `az aks command invoke` / VPN |
| Model provider | Vertex AI (`us` multi-region) via WI | Amazon Bedrock via IRSA (LiteLLM `bedrock/…` profile) | Azure OpenAI via Workload ID (LiteLLM `azure/…` profile) |
| Disk snapshot before scale-down | `gcloud compute disks snapshot` | EBS snapshot / VolumeSnapshot (CSI) | Azure Disk snapshot / VolumeSnapshot (CSI) |
| Node scale to zero | node pool resize 0⇄1 | managed node group desired 0⇄1 | node pool count 0⇄1 (user pool) |

## Steps to add a cloud (not done)

1. `platform/clouds/<cloud>/terraform` produces the contract outputs above.
2. `platform/clouds/<cloud>/kubernetes` overlay:
   - workload-identity annotations
   - storage class
   - provider egress (from `providers/<profile>.yaml` → `egress.fqdn`)
   - API-server egress for the ops agent
3. A renderer applying the same invariant checks as `platform/clouds/gke/render.py` (no LB/Ingress, digest-pinned
   signed images, default deny, PSS restricted, identity only for gateway/redactor).
4. Run `make test-policies` unchanged (it targets the base) and the live attack suite against the new cluster.
