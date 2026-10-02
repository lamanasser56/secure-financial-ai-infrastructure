# Supply-chain policy

The main CI validates source scope, schemas, runtime controls, YAML, documentation links, lint, and Git history secrets. A separate pull-request/manual workflow runs dependency scanning and qualifies Trivy, Syft, and Cosign with public or synthetic inputs. It does not build, publish, sign, or deploy portfolio images.

`requirements-dev.in` is the reviewed authority for direct development and test dependencies. `requirements-dev.txt` is generated with transitive versions and SHA-256 hashes and is the immutable installation authority. Use Python 3.12 and `pip-tools==7.6.1` to regenerate the lock with `python -m piptools compile --generate-hashes --resolver=backtracking --allow-unsafe --strip-extras --index-url https://pypi.org/simple --output-file requirements-dev.txt requirements-dev.in`. Install it with `python -m pip install --require-hashes -r requirements-dev.txt`, then run `bash scripts/check-python-lock.sh`. Regenerate and review the complete lock whenever a direct dependency changes. Cloud-provider SDKs belong in separate optional dependency sets and must not enter this portable core automatically.

The portable lock was generated and verified on the disposable `secure-infra-worker` VM, not the laptop. The VM is an execution worker, not an architectural dependency of this project.

`requirements-google-sdp.in` is the separate optional authority for the disabled Google SDP evaluation environment. It includes `requirements-dev.in` and exactly pins the reviewed `google-cloud-dlp` version. `requirements-google-sdp.txt` is its generated, transitive SHA-256 hash lock. With Python 3.12 and `pip-tools==7.6.1`, regenerate it using `python -m piptools compile --generate-hashes --resolver=backtracking --allow-unsafe --strip-extras --index-url https://pypi.org/simple --output-file requirements-google-sdp.txt requirements-google-sdp.in`; review the diff before installing with `python -m pip install --require-hashes -r requirements-google-sdp.txt`. Run `bash scripts/check-google-sdp-lock.sh` to verify consistency. `scripts/check.sh` checks this optional lock only when `PORTFOLIO_CHECK_GOOGLE_SDP_LOCK=1`; portable core developers do not need the Google SDK. The optional CI job runs offline fake-client tests without Google credentials or API calls. This dependency generation and verification also runs on the disposable `secure-infra-worker` VM; it does not make that worker an architectural dependency.

The optional CI job also validates the [synthetic corpus](../evaluation/google-sdp/corpus.json), exercises the [evaluation harness](../scripts/evaluate-google-sdp.py) with fakes, and runs its default offline mode. It stores only a sanitized temporary result outside Git. The result contract excludes raw input, redacted provider text, detected substrings, encoded or hashed fixture values, credentials and project identifiers. This is harness qualification, not a Google SDP accuracy, image, or release qualification.

`requirements-google-sdp-runtime.in` is the smaller direct dependency authority
for the disabled synthetic evaluation image. Its generated SHA-256 hash lock,
`requirements-google-sdp-runtime.txt`, contains only the evaluation runner's
schema validator and the optional Google SDP SDK with their resolved closure.
Generate and verify it on Python 3.12 with pip-tools 7.6.1 using the same
backtracking, canonical PyPI, and hash options as the other locks. Run
`bash scripts/check-google-sdp-runtime-lock.sh` and install a fresh runtime
environment with `python -m pip install --require-hashes -r
requirements-google-sdp-runtime.txt`. The optional CI job checks this lock;
the portable core remains separate.

The [local evaluation image](../docker/google-sdp-evaluation/README.md) uses
digest-pinned Python and distroless bases, a non-root shell-free runtime, and
network-disabled offline validation. Its [candidate inventory](../docker/google-sdp-evaluation/candidates.json)
records the bounded base comparison and local scan decision. Trivy 0.72.0,
Syft 1.44.0, the current CISA KEV feed, and the unchanged policy evaluator
qualify the local subject with zero HIGH/CRITICAL findings and no exceptions.
This result is tied to that local image digest and point-in-time vulnerability
data. It is not registry promotion: no push, signature, provenance attestation,
deployment, Google API call, or provider authority change is included.

The [qualification scripts](../scripts/) pin scanner versions, require immutable image digests, check declared Python dependencies with OSV-Scanner, scan a public image with Trivy, validate a CycloneDX SBOM from Syft, and test Cosign blob signing and tamper rejection with a temporary key. [Image policy](security/container-vulnerability-release-policy.md) validates exact-subject, time-limited exception records without importing historical approvals. A production pipeline must retain complete scanner outputs and SBOMs, verify image provenance and trusted signatures before promotion, and reject unsigned or mutable image references. Known exploited vulnerabilities and fixable critical findings remain blocking.

Run `bash scripts/install-qualification-tools.sh /absolute/temporary/directory` to install checksum-verified scanner binaries, add that directory to `PATH`, then run `bash scripts/qualify-supply-chain.sh`. Run `bash scripts/scan-secrets.sh` separately with Gitleaks 8.30.1. The public image digests in `kubernetes/` are examples of immutable references. A target deployment must confirm current upstream provenance, platform compatibility, support status, vulnerabilities, and runtime behavior. A successful source test or Kustomize render is not an image release decision.
