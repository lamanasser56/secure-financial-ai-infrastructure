# Real redactor qualification checkpoint

## Decision

**BLOCKED for release or live model use, 2026-10-04.** Presidio remains the sole
runtime redactor. No policy threshold, exception register, authority, deployment
image or SDP wiring changed. The separate nine-case SDP run ended INCONCLUSIVE
and exhausted its 18-attempt budget; its cluster and temporary resources were
removed at the recorded final checkpoint. No SDP rerun is part of this work.

[Machine-readable sanitized qualification](../../evaluation/presidio-bounded/qualification.json)
records exact subjects, complete-scan/SBOM hashes, source-input hashes, findings
and synthetic case results. Full fresh original Trivy reports, SBOMs, current CISA
KEV feed and policy results are retained privately on the worker. Findings below
are package/advisory occurrences, not a count of distinct CVEs. There are no
active risk acceptances. The unchanged [release policy](../security/container-vulnerability-release-policy.md)
and evaluator blocked every candidate.

| Subject | HIGH | CRITICAL | Fixable HIGH/CRITICAL | Policy |
| --- | ---: | ---: | ---: | --- |
| Committed Presidio Analyzer 2.2.362 | 154 | 9 | 111 | BLOCK |
| Committed Presidio Anonymizer 2.2.362 | 156 | 9 | 113 | BLOCK |
| Upstream Analyzer 2.2.364 | 123 | 7 | 78 | BLOCK |
| Upstream Anonymizer 2.2.364 | 110 | 3 | 61 | BLOCK |
| Bounded Presidio 2.2.364 candidate | 47 | 0 | 3 | BLOCK |
| Committed LiteLLM v1.86.2 | 82 | 5 | 86 | Invalid evidence; BLOCK |

These are current qualification results; historical scans are preserved and do
not qualify new image bytes or override database drift. Existing Kubernetes
references are architecture examples, not promoted images or deployed services.

## Concrete candidate and exact blockers

The [bounded candidate](../../docker/presidio-bounded/README.md) builds on the
pinned Python 3.12.15 Debian 13 base, installs the separate hash lock with normal
dependency resolution and `pip check`, and runs actual upstream Presidio engines.
A Docker archive was exported and inspected; linux/amd64 configuration bytes are
bound to `sha256:016631eb3baa6df8d81031720de99776f493ea52259c6bca3ce61967c2887efa`.
The original scan is preserved. A separately labelled policy copy maps its archive
path to that verified **local configuration-digest subject**. Docker's store ID,
configuration digest and any future registry manifest digest are distinct; no
publication, signature or registry equality is claimed. SBOM generation succeeded.

Thirty-one actual Analyzer/Anonymizer HTTP cases passed inside a non-root,
read-only, network-disabled, capability-free container with one CPU, 1 GiB memory,
96 PIDs and 32 MiB temporary storage. They cover the eight existing categories in
English, Arabic and mixed text; three Arabic-digit identifier cases; and four
negative/control cases, including preserved structured financial facts. Only case
IDs/categories/counts were emitted. There were zero external model calls.

The final image still has 47 HIGH findings. Two affect `cryptography==48.0.1`:

| Advisory | Installed | Scanner fixed version | Blocking constraint |
| --- | --- | --- | --- |
| CVE-2026-69247 | 48.0.1 | 50.0.0 | Upstream Anonymizer requires `<49.0.0` |
| CVE-2026-69249 | 48.0.1 | 49.0.0 | Upstream Anonymizer requires `<49.0.0` |
| CVE-2026-103111, libpcre2-8-0 | 10.46-1~deb13u2 | 10.46-1~deb13u3 | Pinned base needs rebuilding/qualification |

The other 44 HIGH findings are unfixed Debian package occurrences in the scanned
base: util-linux family, ncurses, libacl, systemd/udev and perl. See the exact
47-entry package/advisory list in the qualification artifact. The gateway report additionally contains a duplicate finding that the unchanged evaluator rejects; it is not filtered out or accepted. No exception, VEX
assertion or package deletion was used. The official [Anonymizer dependency declaration](https://github.com/data-privacy-stack/presidio/blob/2.2.364/presidio-anonymizer/pyproject.toml)
confirms the cryptography ceiling. Installing a fixed version outside it would
break the declared dependency contract; this milestone does not do that.

## Remediation alternatives

| Option | Work and trade-off | Required gate |
| --- | --- | --- |
| Supported upstream release | Use an upstream release permitting a fixed cryptography version, with a maintained rebuilt base | Fresh lock, normal `pip check`, all detector/failure tests, complete scan/SBOM/KEV and zero-exception policy |
| Explicitly maintained source patch | Review a minimal upstream dependency-range patch with retained attribution and source/wheel provenance | Crypto/API compatibility and regression tests; maintained fork responsibility; same unchanged image policy |
| Minimal/distroless runtime | Reduce OS surface with exact shared-library lineage and runtime tests | Fresh scan; does not itself fix the incompatible cryptography ceiling |
| Wider bilingual NLP/NER | Independently qualify Arabic/mixed-language models and additional entities | Artifact/license/resource review and separate detection contract; larger dependency surface |

The NoOp/pattern profile does not establish names, addresses, OCR, obfuscation or
comprehensive detection. Its labelled bank-account pattern is narrower than the
reference deployment. It is a candidate for bounded synthetic inputs, not an
automatic deployment substitute. Detection success and release-policy failure
are separate outcomes. **No external model path is enabled.**

## Reproduction and retained evidence

Use only the validated worker tools. [The script](../../scripts/qualify-bounded-presidio.py)
requires the actual candidate environment and fixed `/app/server.py`. A reviewed
read-only qualification mount contains only its script, Phase 3 adapters/runtime
and committed synthetic corpus. Run with `--network none`, bounded resources,
`--read-only`, UID/GID 65532, dropped capabilities and no new privileges. No
host port is published. The candidate's service processes are stopped on exit.

The image has not been signed, published or selected by Kubernetes. Private
intermediate scans and the final fresh scan are distinguished. The current UI
remains an offline simulation with simulated identity and redaction doubles.
