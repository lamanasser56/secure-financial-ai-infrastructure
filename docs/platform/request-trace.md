# Request events and worker traces

There is no single independently joined audit trace for every boundary. The Map says **Audit · request events**. A worker's response metadata and independently emitted boundary events have different sources and may use different request IDs.

## IDs and authority

Financial and Guide create a request ID for a turn and pass it through their client transports. The mandatory `GatewayBoundary` generates its own ID, replaces caller metadata and forwards that ID to the private provider path. Broker events use their own trusted identity reference. Do not assume that equal-looking fields establish a verified cross-component join.

The browser's request-trace drawer presents worker-produced metadata, not a signed or independently reconstructed record. The worker can report what it attempted; trusted broker/boundary enforcement must be verified at those components and by the release's tests.

## Financial fields

| Field | Meaning and limit |
| --- | --- |
| `request_id`, `user_ref` | Worker turn ID and pseudonymous reference; no raw user ID or proof of broker identity |
| `outcome`, `reason` | Reported answered/refused/blocked result and closed reason |
| `model`, `model_calls`, `tokens` | Alias/resolved name and reported counts; missing fields are not invented |
| `cost_usd`, `cost_source` | Reported model cost only when supported by its source; absent/invalid cost stays unavailable; a declared zero-call turn can report zero |
| `tool_calls`, `data_access` | Reported registered reads through the trusted broker, not an independent RLS-denial event |
| `grounding_result` | Worker admission result; figure and selected-claim checks do not prove every sentence |
| `redaction` | Reported calls and named category counts; zero findings do not prove that no sensitive content existed |
| `injection_result` | Reported pattern filtering; not proof that every instruction was recognized |

The event schema excludes raw prompts, questions, answers, merchant/note content, credentials and amounts. Schema/content tests do not prove every possible process log is content-free. Credential-pattern scans have their stated scope.

Events can be emitted to stdout and collected by configured cloud logging. This is not a promise of complete capture, durable retention, audit-before-mutation or a joined record of every request. The existing executor replay store serves one-use approval consumption; it is not a general audit collector.
