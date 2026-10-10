# Gate 1: first live bring-up of the agent platform (bundle for owner review)

This is the first cloud gate. Everything before it is implemented and tested offline. One approval of this bundle
covers steps 1–9 below. On any deviation, execution stops and reports back to you; it never improvises.

## What is ready (offline, branch `phase-e-platform`, worktree `../secure-financial-ai-infrastructure-phase-e`, uncommitted)

- **`platform/core` (cloud-agnostic):**
  - namespaces `platform`/`apps`/`ops` (PSS restricted), default-deny NetworkPolicies and explicit paths, quotas
    (LB/NodePort = 0)
  - ops-agent RBAC + ValidatingAdmissionPolicy
  - workloads: gateway, redactor, Postgres RLS, app, ops-agent, fault-demo; programs; Python package
    `agent_platform`; image Dockerfile; dashboard v1 overlay
- **`platform/clouds/gke`:**
  - Terraform module + root (31 resources, see below)
  - overlay; `render.py` (invariant checks), `lifecycle.py`, `attack_suite.py`, user-ADC token guard
- **`providers/`:** `gemini.yaml` (active: `gemini-3.5-flash`, `us`, explicit costs, $10/month) and `claude.yaml` (inactive proof).
- **CI:** `.github/workflows/agent-platform-images.yml` builds app and ops, runs Trivy (fail-closed) and SBOM, pushes by
  digest, signs with keyless cosign, verifies the signature and attests with KMS.
- **Docs:** `docs/architecture.md`, `docs/porting-guide.md`, ADR-008 (Accepted), KMS ownership/rotation, the requalification
  plan, the teardown plan, and `archive/qualification-history/README.md` (honest C record).

## Offline test evidence
| Suite | Result |
|---|---|
| `make test`: unit tests (approvals, diagnosis, actions, agent flow, redaction fail-closed, providers, manifest invariants + 15 mutation rejections, secret separation, front-door approvals, dashboard assets) + Terraform validate/fmt + provider drift | 25 passed (+6 envtest skipped here) |
| `make test-policies`: real kube-apiserver v1.35.0 + etcd (envtest, sha512-pinned); RBAC, VAP and PSS allowed/denied cases as the ops-agent identity | **6/6** |
| Defects found and fixed by these tests | VAP `*/*` rule rejected by the API server; VAP `request.subResource` absent; readiness diagnosis bug |

## Exact IAM diff (all additive; nothing existing is removed or modified)
| Principal | Role / permission | Scope |
|---|---|---|
| new SA `agent-platform-node` | `roles/container.defaultNodeServiceAccount` | project |
| new SA `agent-platform-node` | `roles/artifactregistry.reader` | repository `sdp-evaluation-images` |
| new SA `agent-platform-gateway` | new custom role `agentPlatformPredict` = {`aiplatform.endpoints.predict`, `serviceusage.services.use`} | project |
| KSA `platform/gateway` | `roles/iam.workloadIdentityUser` | on SA `agent-platform-gateway` |
| KSA `platform/redactor` | `roles/iam.workloadIdentityUser` | on the **existing** SA `google-sdp-runtime` (one added member; C's exact-binding verifier is history) |
| new WIF pool `agent-platform-ci` + provider (condition: repository_id = 1401417840 ∧ ref = `refs/heads/main` ∧ workflow = `agent-platform-images.yml`) | n/a | dedicated pool, so the retained C provider can't map here |
| pool principalSet (repository_id 1401417840) | `roles/iam.workloadIdentityUser` | on new SA `agent-platform-ci` |
| new SA `agent-platform-ci` | `roles/artifactregistry.writer` | repository `sdp-evaluation-images` |
| new SA `agent-platform-ci` | `roles/cloudkms.signerVerifier` | KMS key `agent-platform/binauthz-attestor` only |
| new SA `agent-platform-ci` | `roles/containeranalysis.notes.attacher` | attestor note only |
| new SA `agent-platform-ci` | `roles/containeranalysis.occurrences.editor` | project (required to create attestations) |
| new SA `agent-platform-ci` | `roles/binaryauthorization.attestorsViewer` | attestor only |

**Other resources:**

- APIs enabled: binaryauthorization, cloudkms, containeranalysis (`disable_on_destroy=false`)
- network `agent-platform` (no NAT, Private Google Access, flow logs)
- private cluster `agent-platform` with pool `work` (1 × e2-standard-4, 50 GB pd-balanced)
- KMS key ring + key
- attestor + project singleton Binary Authorization policy
- audit log bucket (30 days) + sink

**Expected plan:** about 31 to add, 0 to change, 0 to destroy. `lifecycle.py apply` refuses any destroy or replace.

## Steps (in order; I run them, you only do the items marked **you**)

1. **you:**
   - approve a local commit, a push of branch `phase-e-platform`, and a fast-forward PR into `main`.
     `origin/main` is an ancestor (+21 C commits, then Phase E).
   - set three GitHub repository variables after step 3: `AGENT_PLATFORM_PROJECT_ID`, `AGENT_PLATFORM_CI_WIF_PROVIDER`,
     `AGENT_PLATFORM_CI_SERVICE_ACCOUNT`. Or approve `gh variable set`.
2. **Read-only:**
   - select the exact REGULAR-channel GKE 1.35 version (serverConfig)
   - check masar-gke's Binary Authorization mode: the new project policy only applies to clusters with
     `PROJECT_SINGLETON_POLICY_ENFORCE`, and masar-gke is at 0 nodes
3. `make plan`, then `make apply`, using the reviewed plan only. The summary JSON is shown before apply.
4. **you:**
   - `gcloud auth application-default login` (user ADC for Terraform; already used by the token guard)
   - later, at `make up`, type the operations-approval passphrase once (`! make secrets` in this session)
5. CI run on `main` builds, scans, signs and attests `agent-platform-app` and `agent-platform-ops`. I copy their digests
   into `platform/clouds/gke/images.json`.
6. `make attest` for the three reused C-qualified digests (gateway, database, redactor), after verifying their existing cosign signatures.
7. `make up` (scale 0→1, render + validate, apply, secrets, bootstrap, rollouts). Target: about 15 minutes.
8. **Requalification** (≤ 30 requests; `docs/agent-platform/model-requalification.md`), then **DoD 1–3** live (a financial
   question in your words; `make fault` → detect → you approve in the UI → remediate → verify; denials), then `make attack`.
9. `make down` (Postgres snapshot, scale to 0). Then a read-only `make inventory`.

## Cost of this gate
| Item | Estimate |
|---|---|
| Cluster session, about 4 h | ≈ $0.6 |
| Requalification + attacks | ≈ $1–3 of model spend (key budgets cap it at $10/month) |
| Idle after `make down` | ≈ $0.1–0.2/day; +$2.40/day while masar-gke still exists (two clusters exceed the free tier) |

## Risks to watch at the gate

1. Trivy is fail-closed. Unfixed upstream CVEs in the reused dependency set could block CI. Fallback: the repo's exact-scope
   policy evaluator with an explicit register (your decision).
2. Reaching `aiplatform.us.rep.googleapis.com` and `dlp.us-east1.rep.googleapis.com` through Private Google Access with
   no NAT is proven by the attack suite's gateway positive control. If it fails, `make down` and fix offline.
3. Binary Authorization project policy: confirm at step 2 that masar-gke doesn't evaluate it.
4. The app UI over port-forward depends on loopback/Host behaviour. Proven offline only.
5. The model was never called through this path before the requalification run.

## Decisions needed (all in this one checkpoint)

1. Approve this bundle (steps 1–9), including commit + push + PR to `main` and the IAM diff above.
2. GitHub variables: you set them, or approve `gh variable set`.
3. Trivy fallback if CI blocks: allow the exact-scope evaluator with a register, or stop.
4. Removed from your checklist: `gke-gcloud-auth-plugin`/sudo is no longer needed (kubectl uses a per-call gcloud token),
   and nothing runs in Cloud Shell.
