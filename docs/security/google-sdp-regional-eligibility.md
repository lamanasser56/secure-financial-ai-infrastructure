# Read-only regional eligibility assessment

Assessment date: 2026-10-03. Environment-specific identities, billing account IDs and payment details are excluded. Original audit and execution evidence remains private and unchanged.

| Question | Verified fact or remaining uncertainty |
| --- | --- |
| Observed failure | One `storage.buckets.create` attempt in `me-central2` returned HTTP 403: `Permission denied on 'locations/me-central2' (or it may not exist).` Audit status code 7 at `2026-10-03T09:32:53.380208959Z`. |
| IAM | The audit records `storage.buckets.create` as granted. This is evidence about that permission, not proof of every bootstrap permission. |
| Resulting resources | Exact bucket lookup returned 404. No bucket, Terraform resources, backend state, release or evaluation cluster resulted. |
| Project location policy | Authorized effective `constraints/gcp.resourceLocations` read returned `allValues: ALLOW`. No location restriction from this constraint was observed. The newer Org Policy API was disabled; the legacy Resource Manager read succeeded without enabling it. |
| Billing | Project billing enabled; linked account open, currency USD. Owner reports country USA. Public Billing API metadata does not identify self-serve versus invoiced; account type and Dammam entitlement remain unconfirmed. No payment profile or payment details were accessed. |
| Dammam | Google's non-KSA guidance limits Dammam to invoiced accounts. The Storage failure is compatible with a regional entitlement issue, but does not prove its exact cause. No KSA/CNTXT requirement is inferred for this USA account. |
| us-east1 | Official docs list SDP regional support, Artifact Registry and Cloud Storage. Authorized project Artifact Registry location metadata lists `us-east1`; Compute region reports `UP`. Effective location policy permits it. No documented Dammam-specific purchase gate applies to this proposed location. |
| Unproven | Actual us-east1 bucket creation, registry provisioning, quotas, SDP authorization/transport and live operation success. No write probe or SDP call was made. |

[Dammam access](https://docs.cloud.google.com/docs/dammam-region-access), [Billing account metadata](https://docs.cloud.google.com/billing/docs/reference/rest/v1/billingAccounts), [billing account types](https://docs.cloud.google.com/billing/docs/how-to/manage-billing-account), [SDP locations](https://docs.cloud.google.com/sensitive-data-protection/docs/locations), [regional endpoint names](https://docs.cloud.google.com/docs/security/compliance/regional-service-endpoints), [Artifact Registry locations](https://docs.cloud.google.com/artifact-registry/docs/repositories/repo-locations), [Storage locations](https://docs.cloud.google.com/storage/docs/locations).

If historical Dammam eligibility needs confirmation, the owner must check Google Cloud Console → Billing → the account linked to the project → Account management/overview. Exact question: **Is this USA billing account Self-serve/Online or Invoiced/Offline, and, if invoiced, is Dammam access enabled for this account/project?** If the UI cannot establish the entitlement, ask Google through the owner's existing support channel. No external party has been contacted. This optional historical clarification is not a prerequisite for preparing us-east1; no billing change or KSA/CNTXT onboarding is proposed.

## Decision

Dammam execution cannot resume on the available evidence. Prepare the complete [us-east1 amendment](../architecture/decisions/ADR-005-us-east1-synthetic-sdp-evaluation.md), retaining security controls and historical evidence. Read-only checks support the proposed location and show no project location-policy prohibition; they do not guarantee service access. The previous Dammam approval does not authorize this execution. No Saudi-residency or SDP accuracy claim is made.
