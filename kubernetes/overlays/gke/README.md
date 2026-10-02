# GKE network pattern

[NodeLocal DNS allowance](allow-nodelocal-dns.example.yaml) is an example only. Replace the listener CIDR after inspecting the actual cluster. Keep the portable kube-dns selector and default-deny policies; test DNS resolution and denied egress with the target CNI. This directory does not install GKE Ingress, Workload Identity or storage resources.
