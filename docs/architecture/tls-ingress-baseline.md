# TLS and ingress baseline

An integrating application must choose an ingress controller or managed load balancer, public DNS ownership, certificate issuance and renewal, and the route from the edge to application-owned services. Terminate TLS only at an approved edge and define whether internal hops require TLS as part of the deployment design. Redirect cleartext entry, restrict administrative endpoints, and verify certificate renewal and expiry alert delivery.

The AI services in the [Kubernetes base](../../kubernetes/base/) are internal ClusterIP services. They have no public ingress. The standalone repository does not select an edge controller, domain, certificate issuer, or product route. The source project's temporary Traefik HTTP demo is obsolete and was excluded.

Before exposure, test the target ingress policy, allowed source paths, TLS protocol and certificate chain, gateway authentication, rate limits, and logging redaction. A rendered Kustomize base does not prove any of these edge controls.
