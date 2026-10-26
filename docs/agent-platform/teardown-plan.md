# Retention, assessment cleanup and teardown

There is no automatic teardown authorization in this document. A historical target date or credit-expiry note does not authorize deletion. Review actual resource ownership and the current owner request before any destructive work.

## Persistent engineering resources

**Keep `secure-infra-worker`, `sfai-engineering` and their retained disks until the owner explicitly requests deletion.** The all-image build theme runs on `secure-infra-worker`; current offline tests use `sfai-engineering`. These VMs are outside the platform workload boundary and outside disposable assessment cleanup. Stopping a VM and retaining its disk is distinct from deleting it.

## Disposable assessment

The final assessment uses its own disposable project and the approved operator/janitor controls, synthetic data, zero external LLM calls and the same bounded rules/ceilings as the 25 October run. Its cleanup must remove its resources and unlink its billing. Cleanup targets must identify that disposable project explicitly; they must not be inferred from a current CLI default or expanded to the original platform project or persistent worker VMs.

Preserve sanitized evidence of source/image subjects, exercised controls, failures, cleanup and billing unlink. An incomplete cleanup is not a completed assessment.

## Platform lifecycle

`make down` snapshots the declared database and scales the platform down; it is not a whole-project teardown or a VM-deletion command. A snapshot is not a proven restore. Keep the selected release/evidence and private operator state separate from public source.

A future platform teardown needs a fresh, concrete owner-approved resource inventory and dependency order. Review cluster/storage, private endpoints/DNS, registry/signatures/attestations, identities and state separately. Never use the old broad cleanup lists as authorization to remove unrelated projects, retained VMs or disks. Export required evidence and validate the exact targets before any irreversible deletion.

`make inventory` is an inventory aid, not a command to delete everything listed or proof that every listed resource belongs to this platform. A retained worker is an intentional exception to a disposable assessment's empty-resource result, because it is outside that project's cleanup scope.
