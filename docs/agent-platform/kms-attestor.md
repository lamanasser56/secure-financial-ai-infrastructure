# Image attestations and source proof

The image pipeline signs exact published digests with keyless cosign and creates Cloud KMS-backed Binary Authorization attestations. Readiness must verify the exact subject, expected signer/workflow identity, expected attestor/note/key and cryptographic payload. Presence of an attestation record alone is insufficient.

These evidence types are distinct:

| Evidence | Establishes | Does not establish alone |
| --- | --- | --- |
| Image digest | Exact image bytes | Approved producer, safe contents or source commit |
| Keyless signature/certificate | Signature over the subject and the verified workflow identity/certificate claims | Which checkout/materials the build actually used |
| KMS Binary Authorization attestation | The approved attestor's signed statement for the exact image subject | Source-tree provenance or a full live security pass |
| Verified source provenance | Subject-to-builder/material/source binding under its trusted identity | That every application behaviour is correct |
| Selected release/runtime observation | Intended digests and observed running state in its scope | A substitute for the cryptographic proofs or an assessment |

`agent_platform.release_verify` and the current image/release workflows own the executable verification. Keep private project/key/identity values in owner configuration, not documentation or recorded output. No static private signing credential belongs in an image or worker checkout.

For the final release, freeze source S, build first-party images from it, verify subject/source binding, promote lock/evidence metadata in R and deploy the same digests. A workflow certificate revision must not be mistaken for checkout-source proof. Historical qualification, a source field in an unsigned receipt and a mutable tag are not substitutes.
