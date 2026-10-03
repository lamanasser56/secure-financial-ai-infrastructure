# Disabled Google SDP evaluation image

This image runs only the synthetic corpus validator by default. It has no
provider credentials, network service or production redaction route. Its separate
execution package remains unapplied. A live evaluation still requires the runner's explicit `--live` mode,
synthetic-only acknowledgment, a separately supplied trusted project identity,
and a separate authorization. This Change Set performs none of those actions.

The [Dockerfile](Dockerfile) pins the Python 3.12 builder and Debian 13
distroless runtime by digest. The runtime copies CPython, the locked Python
closure, and two native libraries needed by gRPC. It runs as UID:GID
`65532:65532`, has no shell or package manager, and uses a read-only application
tree. The [candidate record](candidates.json) records the bounded base-image
comparison and local qualification evidence. Base digests and vulnerability
results are point-in-time observations; refresh and requalify before use.

Live preparation preserves the nine-case corpus, rejects changed live inputs,
sets a 20-second RPC deadline, and reports sanitized SDK invocation attempts.
Those counters are not proof of server receipts. The fixed timestamp is passed
explicitly as a BuildKit build argument as well as rewriting layer timestamps.
See the [integrated readiness record](../../docs/security/google-sdp-milestone-readiness.md)
for authentication, egress, release approval and evidence prerequisites.

Build on a linux/amd64 worker with Docker Buildx and Python 3.12:

```bash
bash scripts/build-google-sdp-evaluation-image.sh \
  python:3.12.15-slim-trixie@sha256:29113dcae7aad06daa8e95260fa09f27d62be33b9687ea3774f771d601a02256 \
  gcr.io/distroless/base-debian13:nonroot@sha256:a0d70d6a97cd697d9362bc2aae4a6560dd65817e365d0043b07325a97975dc91
```

The script checks both explicit references against the candidate record and
Dockerfile, builds only for linux/amd64 with a fixed source date and rewritten
file timestamps, checks the runtime UID and file list,
and runs default offline validation with container networking disabled. It
prints the local image tag, image ID, and RepoDigest if Docker supplies one.
It does not push or sign an image. The local digest is the qualification
subject for the local scan and SBOM; it is not a registry release digest.

The [configuration reader](../../scripts/google-sdp-image-config-id.py) hashes
the configuration bytes in the Docker archive. Docker's `.Id` can denote a
manifest with the containerd image store, so it is not used as a portable
configuration identifier. The candidate record separately retains the
observed image-store ID, local subject and configuration digest. A fresh
uncached build reproduced the same configuration and rootfs identities;
registry digest equality is not assumed.

For qualification, scan the exact local image subject with Trivy 0.72.0, generate a
CycloneDX SBOM with Syft 1.44.0, and run the existing
[vulnerability policy evaluator](../../scripts/evaluate-container-vulnerability-policy.py)
against the complete Trivy JSON, a current CISA KEV feed, and the empty
[exception register](../../policy/empty-exceptions.json). The source
[release policy](../../docs/security/container-vulnerability-release-policy.md)
still requires provenance, signature, and same-digest promotion evidence for
any future release. No registry publication or deployment is authorized here.

## Trusted evaluation location

The image includes the closed [deployment contract](../../evaluation/google-sdp/deployment.json)
and its [schema](../../evaluation/google-sdp/deployment.schema.json). The disabled
adapter selects only `us-east1` and `dlp.us-east1.rep.googleapis.com` at startup;
requests and environment variables cannot select another location. Missing or
invalid configuration fails closed before SDK construction. The build content
key covers these files. [ADR-005](../../docs/architecture/decisions/ADR-005-us-east1-synthetic-sdp-evaluation.md)
supersedes the historical Dammam location; its previous qualification evidence
remains preserved outside Git and in source history. Image contents changed, so
fresh configuration reproduction, SBOM, scan and unchanged policy evidence are
required for this amended image. No registry digest, signature, regional live
access, Saudi residency, SDP accuracy or Presidio cutover is proven locally.

## Amended local qualification

Worker-only qualification reproduced configuration digest
`sha256:8646533e6d89a7ff58773bd77b0752d8203a94e6a838bf4b3a59b4b0769444ef`
in a separate fresh BuildKit cache. The observed Docker image-store identity is
`sha256:8ed226a3b5f310aa06bf02ac3fd85b5eeddd108fb2f89cf8bb14d52ae5bdd5cc`.
The exact local policy subject uses the configuration digest; the original
Trivy target is preserved in private evidence and only `ArtifactName` is
relabeled for the unchanged exact-subject evaluator. SBOM contains 1363
components; Trivy reports zero HIGH/CRITICAL, 15 MEDIUM and eight LOW, with zero
exceptions. See [qualification hashes and scanner timestamps](candidates.json).
The historical Dammam image/configuration/scan evidence remains preserved.
No registry manifest digest equality, signature or live result is asserted.
