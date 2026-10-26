# Porting boundary

GKE is the implemented cloud deployment. EKS/AKS or another provider is not a qualified deployment merely because core code uses Kubernetes APIs.

A port must supply and test: workload networking and DNS/egress; model/DLP private connectivity and identity; image admission and cryptographic release evidence; Secret/state storage; database bootstrap/RLS and capability routing; independent executor RBAC/admission; owner deployment/readiness/reset/assessment operations. Preserve the trusted model, data and mutation boundaries in [architecture](architecture.md).

Use a cloud-specific renderer/module and explicit interfaces, rather than patches to generated YAML or source overlays. Test the current rendered objects against a real API server, then qualify exact built images and actual network paths in the target environment. Provider substitutions, model changes and source changes require their own scoped evidence.

The selected release lock remains the deployment authority. A legacy image-default file, old live result or a declared provider profile does not prove a port works. Historical cloud experiments stay outside the Guide's current corpus. Engineering cleanup need not wait for platform teardown, and a port does not authorize deleting retained worker VMs.
