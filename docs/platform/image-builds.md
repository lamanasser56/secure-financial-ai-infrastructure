# Image build inputs

`platform/image-targets.json` owns first-party build names, Dockerfiles, stages and the optional source argument. It is not a second set of deployment digests. The selected release lock owns deployment selection; changing that lock alone does not change image content inputs. The inventory declares all seven first-party release subjects: App, Ops, Financial, Guide, gateway, redactor and database. The current-source recipes are checked against the workload image names; the lock still selects only verified deployment digests.

## Derived ownership

`tools/image-inputs` uses the pinned BuildKit Dockerfile parser and Moby ignore matcher. It follows the selected stage, its inherited stages, `COPY --from` dependencies and context bind mounts. It enumerates reachable context copies after the effective ignore file; a Dockerfile-specific ignore takes precedence over the root ignore. Directory and wildcard sources include the copied descendants. Referenced external image materials must be digest-pinned.

These are Docker's [documented context and ignore rules](https://docs.docker.com/build/concepts/context/), implemented with its [Dockerfile instruction parser](https://github.com/moby/buildkit/tree/v0.34.1/frontend/dockerfile/instructions) and [ignore matcher](https://github.com/moby/patternmatcher/tree/v0.6.1). Unsupported dynamic source expressions, source symlinks, ADD, ONBUILD and source-relative COPY exclusions fail planning rather than silently omit inputs. New recipe features require supported, tested ownership semantics before use.

The fingerprint includes sorted input paths, file modes and content hashes; Dockerfile, effective ignore and declared qualification/build controls are inputs too. Upstream image references are recorded as materials. Generated output is traced through its builder-stage copies: the Guide index consumes the builder, current corpus manifest, producer and copied documentation. Files copied into a builder still count even when a generator ultimately ignores them. This is a conservative build-input graph, not a claim that every copied byte is executed or remains in the final layer.

The App context explicitly admits agent manifests, not every file below their parent directories. Shared assets are attributed to their actual COPY consumers. Rename, deletion or mode/content changes alter ownership fingerprints. Missing required copies or controls fail the plan. Ignored evidence, private handoffs and dependencies do not join implicitly.

## Workflow decisions

The image workflow builds only a source commit with successful main-push CI. It computes the current complete input plan and compares it with the `image-input-plan` artifact from a successful run of the same trusted image workflow on main in this repository. A successful CI push alone is not a build baseline. Failed image runs cannot advance it. Missing, expired, truncated, inconsistent or untrusted plan data cause every current target to build. The downloader reads one bounded ZIP member as data; it never extracts or executes artifact contents.

The sole target inventory produces the workflow matrix. There is no separate workflow image list or blanket docs skip expression. Documentation changes rebuild their actual consumer; lock/evidence-only promotion outside all copied inputs and controls yields an empty matrix. Manual dispatch forces every target, including the final source freeze build. Source metadata such as the selected commit changes when an image is built; reusing unchanged inputs retains that image's original build source and requires its original evidence.

Every build receives a fresh export of the exact Git source snapshot. Untracked files and later checkout edits are not an overlay on that context. The Guide receives the validated commit as its declared source argument. Each Docker build runs in the existing GitHub-hosted image matrix with a digest-pinned BuildKit image, before the job receives cloud credentials. The job hashes the source archive, scans the local image, generates a CycloneDX SBOM, then runs the same post-push gate. The existing all-severity scan and HIGH/CRITICAL-or-any-KEV policy stay unchanged; planning does not waive qualification.

## Evidence boundaries

An input plan records the snapshot compared and content ownership. It is not an image receipt and does not prove that an image was built, signed or deployed from that snapshot. Release evidence separately binds the exact Git source and archive hash, hosted build environment, input fingerprint, pinned external materials and exact subject digest in a signed custom source predicate. The release verifier checks that predicate against the exact digest, along with the signature and KMS attestation. The build and post-push gates inspect every severity and block HIGH/CRITICAL or any KEV match under the existing policy. Release evidence separately lists remaining findings without available fixes for each image.

The final release sequence still freezes source S, force-builds all first-party images from S on GitHub-hosted runners, verifies exact subjects, and promotes only lock/evidence metadata in R. Deploy those same digests. A changed content input after S requires another freeze and build; a successful planning skip is not permission to relabel an earlier image as built from S.

## Checks

`scripts/check.sh` runs uncached Go tests for current recipes, stage/COPY/ignore ownership, generated inputs, shared assets, source snapshot isolation and conservative selection, plus Python tests for trusted baseline transport. CI installs the compiler version declared in the module and resolves checksum-locked dependencies. The recording gate inventory must include these checks; an unavailable compiler is a failed prerequisite, not a full pass.
