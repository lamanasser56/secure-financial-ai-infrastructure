# Kubernetes network boundary

The base namespace has default-deny ingress and egress, a DNS allowance, and narrowly selected in-cluster client paths for Presidio and LiteLLM. The AI services are ClusterIP only. A client must carry the relevant approved label and still pass application or gateway authentication; a label is not identity proof by itself.

The gateway requires approved HTTPS egress and, on some GKE modes, metadata-server access for Workload Identity. A Kubernetes NetworkPolicy cannot restrict public egress by DNS hostname and only works if the target CNI enforces it. The [NodeLocal DNS pattern](../../kubernetes/overlays/gke/allow-nodelocal-dns.example.yaml) is excluded from the portable base pending cluster-specific addresses.

Ingress, TLS, monitoring scrapes, database access, backup traffic and provider egress need explicit target-environment policies and validation. The temporary HTTP Traefik demo from the source project is intentionally omitted.
