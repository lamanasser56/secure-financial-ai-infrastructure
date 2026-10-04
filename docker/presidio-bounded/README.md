# Bounded Presidio candidate

**Quarantined local candidate. Release policy blocks promotion.** It is not the
committed Kubernetes image, an authorized deployment or a live-agent switch.
The CLI/UI keep their explicit offline simulation. Presidio remains authoritative;
Google SDP's separate evaluation was inconclusive and provides no replacement.

## Implementation and coverage boundary

The image installs hash-locked upstream Presidio Analyzer and Anonymizer 2.2.364.
The small HTTP wrapper calls their actual engines. It has two startup roles,
`analyzer` and `anonymizer`, fixed ports 3000/3001, bounded bodies/results,
no request logging and no outbound client. Bind any future host ports to loopback.
Run non-root with a read-only root, no capabilities, bounded memory/CPU/PIDs and
bounded temporary storage. No service is started by the normal demo entry points.

The detector profile covers the existing eight-category Phase 3 contract only:
email, Saudi phone, checksum-valid card/IBAN, synthetic Saudi national/resident/VAT
formats and explicitly labelled bank-account numbers. English and Arabic
recognizers both run on every text, including history, facts and final answers.
Identical findings are deduplicated; conflicting spans fail the existing validator.
The UI language cannot select detectors or provide fallback authority.

This candidate uses upstream `NoOpNlpEngine`, not an NLP/NER model. Language-specific
recognizers perform real pattern/checksum detection; it has no names, addresses,
NER/context enhancement, OCR or general obfuscation coverage. Saudi patterns are
format checks, not verification of government IDs. The bank pattern requires one
of its committed English/Arabic labels; it is narrower than the reference
manifest's broad numeric pattern. It cannot silently replace that deployment.
The email subclass preserves upstream matching and uses offline suffix validation,
following the existing repository pattern. No external suffix fetch occurs.

The upstream [language configuration](https://github.com/data-privacy-stack/presidio/blob/2.2.364/docs/analyzer/languages.md)
and [NoOp implementation](https://github.com/data-privacy-stack/presidio/blob/2.2.364/presidio-analyzer/presidio_analyzer/nlp_engine/no_op_nlp_engine.py)
explain these limits. Upstream code/packages retain their MIT attribution; the
wrapper is portfolio-owned. Dependencies are installed normally with hash checking,
binary wheels and `pip check`; no dependency is silently removed or overridden.

## Reproduce on the worker

Use the validated Python 3.12/pip-tools 7.6.1 environment and existing Docker/Trivy/
Syft tooling. Do not install or build on the laptop.

```bash
bash scripts/check-presidio-runtime-lock.sh
docker build --platform linux/amd64 -f docker/presidio-bounded/Dockerfile \
  -t portfolio-presidio-bounded:local .
```

The Dockerfile-specific ignore file excludes everything except its exact runtime
lock and wrapper; the SDP build's global ignore file remains unchanged.
[The qualification script](../../scripts/qualify-bounded-presidio.py) starts actual
Analyzer/Anonymizer HTTP processes inside this image, with networking disabled
and only its committed script/runtime/corpus mounted read-only. It emits case IDs,
categories and pass counts; no corpus text, redacted text or protected values.
It performs no external model request. See the [qualification assessment](../../docs/agents/redactor-qualification.md)
for exact invocation, digest linkage, fresh findings and remediation choices.
Passing these synthetic cases never overrides a blocked image policy.
