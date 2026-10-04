# SDP provenance decision: bounded research pass

Retrieved/reviewed **2026-10-04**. Scope: the five blocked Saudi classes, Saudi
phone representations and the existing literal `[at]`/`[dot]` requirement. Reuses
the [prior provenance register](google-sdp-agent-coverage.md). This pass ends with
decisions below; it does not request real customer examples or generate plausible
identifiers. No identity/number verification API or external party was contacted.

## Four separate questions and decisions

| Class | Official format | Official validation/checksum | Official non-assigned test provenance | Meaningful safe fixture / decision |
| --- | --- | --- | --- | --- |
| `IBAN_CODE` (Saudi) | SWIFT registry, country section 2.72: length 24; `SA2!n2!n18!c`, with two-digit bank identifier in BBAN. SAMA documents presentation. | SWIFT FAQ identifies ISO 7064 MOD-97-10 for check digits; arithmetic validity is not account existence. | Registry account examples are not guaranteed non-assigned; no safe Saudi range established. | **UNRESOLVED safety**: no new positive. Do not use a randomly checksum-valid account, zero-filled account, invalid checksum or foreign IBAN as Saudi accuracy proof. |
| `SAUDI_NATIONAL_ID` | HRSD FAQ supports a ten-digit identity/residence input. That does not establish a distinct national-ID prefix/profile. | No authoritative national-ID checksum procedure established in this pass. | No authority-certified non-assigned values/range established. | **UNRESOLVED definition and safety**: no pattern or positive fixture. Previous locally generated Presidio examples remain separate evidence, not provenance. |
| `SAUDI_RESIDENT_ID` | Same HRSD ten-digit input statement; distinct resident-ID semantics/prefix not established from issuing-authority rules. | No authoritative resident-ID checksum established. | No certified non-assigned values/range established. | **UNRESOLVED definition and safety**: no copy of third-party validators or plausible generated number. |
| `SAUDI_VAT_ID` | ZATCA XML standard v1.2, BR-KSA-40/44: 15 digits, first/last digit 3 for the stated domestic invoice fields. | Those rules establish shape, not a published checksum or proof of registration. | No non-assigned VAT value established. Sandbox test certificates do not certify that the accompanying VAT number is fictitious. | **UNRESOLVED safety/validation**: a shape-only expression is insufficient; no positive/custom detector imported. |
| `SAUDI_BANK_ACCOUNT` | SWIFT defines the Saudi BBAN structure used within IBAN. It does not define every bank's domestic account reference. | No universal domestic-account checksum established. | SAMA describes a simulated open-banking lab, with access through its team; no public safe account dataset/usage contract established. | **UNRESOLVED profile and safety**: preserve separate account class; no universal account regex, no IBAN alias or arbitrary business number substituted. |
| `PHONE_NUMBER` (Saudi variants) | CST RR08 fifth edition, February 2024 documents service numbering structures. Exact chosen country/numeral/spacing profile still needs review; PDF body retrieval was intermittent. | No telephone checksum inferred; number shape does not prove allocation/existence. | No Saudi fictional/nonworking test range established by the consulted sources. Unallocated or reserved-for-future-service blocks are not assumed safe indefinitely. | **UNRESOLVED Saudi accuracy**: retained NANPA fictional positives test US formats only; no random Saudi subscriber number or descriptive placeholder added. |
| `EMAIL_ADDRESS` obfuscation | Literal `[at]`/`[dot]` ASCII representation is an explicit repository requirement, not a universal email standard. | Exact span/preservation assertions; no account-existence check needed. | RFC 2606 reserved domains already establish safe inputs. | **PREPARED candidate**: three existing EN/AR/mixed fixtures have exact spans; bounded custom expression added unwired. SDK message shape and local expression tests do not prove live Google accuracy. |
| `CREDIT_CARD` (retained control) | Official Stripe test-mode card values; no new format/network assertion. | Existing reviewed exact spans and matched negatives; no payment/issuer validation request. | Previously verified official non-production test cards. | **PREPARED offline only**: retain existing EN/AR/mixed fixtures; Google accuracy and broader networks/representations remain unqualified. |

The sources do not prove that no safe official dataset exists anywhere. They prove
only the stated positive claims and this pass's remaining uncertainty. Source
samples, search snippets and screenshots never supply permission/non-assignment.
Invalid-format cases can exercise rejection only; placeholders can exercise policy
or plumbing only. Neither fills a required valid-format positive cell.

## Exact primary-source register

| Source | Supported claim / retrieval limitation |
| --- | --- |
| [SWIFT registry PDF](https://www.swift.com/fr/swift-resource/9606/download), section 2.72, page 79 | Saudi length/BBAN/IBAN structure. Examples not imported; non-assignment not asserted. English landing download failed; official French-path PDF contains the English registry. |
| [SWIFT IBAN FAQ](https://www.swift.com/sites/default/files/documents/swift_solutions_faq_ibanplus.pdf) | Names MOD-97-10 / ISO 7064. Does not certify a safe test account. |
| [SAMA printed IBAN formats](https://rulebook.sama.gov.sa/en/printed-iban-account-formats) | Previously verified presentation convention retained; example is not safe-test authorization. |
| [HRSD SSO FAQ](https://sso.hrsd.gov.sa/FAQ) | Official indexed text states ten-digit ID/residence input. Direct fetch returned no body; treat prefix/checksum assertions as unverified, not authoritative issuing rules. |
| [ZATCA XML standard](https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20220624_ZATCA_Electronic_Invoice_XML_Implementation_Standard_vF.pdf), page 58, BR-KSA-40/44 | Domestic invoice VAT field shape. No safe-value guarantee or checksum inferred. |
| [ZATCA sandbox manual](https://sandbox.zatca.gov.sa/20220623_Developer%20Portal%20User%20Manual_vF.pdf) | Indexed text distinguishes test certificates and VAT identity; direct access returned 403. No complete manual claim or sample credentials imported. |
| [SAMA open banking](https://www.openbanking.sama.gov.sa/) | Lab simulates banking APIs; access requires its stated contact route. No outreach, login or test-data retrieval occurred. |
| [CST RR08 numbering plan](https://www.cst.gov.sa/-/media/cst-website-app/data/media/files/National-Numbering-Plan.ashx) and [decision](https://www.cst.gov.sa/en/regulations-and-licenses/decisions/Regulation-1503) | Fifth edition and service-specific structures documented; body fetch intermittently timed out. No safe subscriber reservation or numeric fixture adopted. |
| [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606) | Retained reserved-domain provenance for normal/obfuscated mailbox fixtures. |
| [NANPA fictional range](https://nanpa.com/numbering/555-line-numbers) and [Stripe test cards](https://docs.stripe.com/testing) | Retained verified generic US phone and test-card provenance; neither establishes Saudi phone coverage or Google accuracy. No repeat search or payment call. |
| [Google custom regex](https://docs.cloud.google.com/sensitive-data-protection/docs/creating-custom-infotypes-regex) | Inline `CustomInfoType` name/pattern/likelihood mechanism; not Saudi rules or accuracy. Candidate uses no stored detector creation. |

No further search/tag/build loop is part of this pass. An eventual authority-certified
safe dataset may reopen the relevant decision, with its exact source and conditions.
For this checkpoint the decision is **full qualification BLOCKED**, with **42 prepared,
45 unprepared, 87 planned** unchanged. No new fixture claims are made.

## Candidate email definition and preservation

[Versioned expression](../../evaluation/google-sdp-agent/obfuscated-email-candidate.json)
recognizes only bounded ASCII mailbox/domain text separated by literal `[at]` and
`[dot]`, with bounded horizontal spaces. Neutral category: `EMAIL_ADDRESS`;
custom name: `PORTFOLIO_OBFUSCATED_EMAIL`. The expression adds no authority to the
current adapter. Future mapping, replacement token and span/preservation scoring
must be reviewed together; unknown types still fail closed today. The original
candidate image bytes/evidence remain valid and are not rebuilt for this unshipped
configuration. Parentheses, Arabic mailbox/domain text, arbitrary encoding and
general obfuscation remain unsupported/unqualified, not silent passes.

See the [proposed scope ADR](../architecture/decisions/ADR-006-redaction-qualification-scope.md)
for the concrete owner decision. Resolving provenance alone also leaves all privacy,
latency, completeness, audit, identity, gateway, model and operational gates open.
