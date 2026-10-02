# ADR-003: Evidence-bound image promotion

**Status:** Design; no production image promotion is implemented here.

Every releasable image needs an immutable digest, complete vulnerability report, SBOM, provenance, policy decision and verified signature. New findings fail closed. Known-exploited and fixable critical findings cannot be excepted. An exception requires an exact current subject and finding scope, owner, justification, evidence and expiry; old project approvals never transfer to this repository.

The local [qualification scripts](../../../scripts/) exercise parts of this chain with public synthetic inputs. Target images and publication require separate integration.
