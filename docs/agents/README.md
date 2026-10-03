# Bounded demo agents

Two read-only demonstrations reuse the existing secure runtime. They were built after the synthetic SDP evaluation's final cleanup checkpoint. Neither entry point restarts that evaluation or creates cloud resources. Presidio remains authoritative; Google SDP is disabled and unwired into the agent path.

## Implemented

- One bounded core composes the Phase 3 runtime and canonical Phase 4 registry, invocation, injection, policy, approval and AI-audit controls.
- Infrastructure diagnostics reads three approved synthetic CI scenarios, a synthetic image qualification summary and bounded runbook sections. It suggests repairs and executes none.
- Financial analysis uses two isolated synthetic tenant fixtures. Tools calculate integer SAR minor-unit totals, counts and category rankings. The simulated model explains those facts.
- Separate server-selected identities, policy profiles and tool allowlists. The financial profile has no infrastructure permissions.
- Runnable CLIs and a loopback-only Arabic RTL/English UI with keyboard-operated tabs, labelled controls, status announcements and text-only result rendering.
- Offline adversarial tests for request/proposal/schema containment, tenant context, redaction, evidence references, budgets, deadlines and HTTP boundaries.

**Every CLI/UI result is an offline simulation.** Authentication is simulated. The deterministic `FakeGateway` sends no HTTP request and truthfully records `provider_called=false`. The demo exercises the existing `PresidioRedactor` composition with explicitly synthetic analyzer/anonymizer test doubles. Its email pattern is not evidence of real Presidio coverage, Arabic detection, production security or model accuracy.

## Designed

The same core can compose integration-supplied real identity/tenant/authorization adapters, real Presidio services and the existing LiteLLM HTTP adapter. `prepare_gateway_core` is an integration factory; the CLI/UI expose no live mode. Both profiles would use the existing `secure-financial-chat` alias through LiteLLM. Gemini via Vertex AI is the intended gateway provider. Agents contain no direct provider SDK or Google credential handling.

See [live integration prerequisites](live-integration.md). No live provider request or cloud/IAM change was performed for this implementation.

## Integration-dependent

Real authentication and trusted tenant resolution, scoped gateway virtual keys, gateway/provider identity, qualified model/region, real Presidio service availability and language coverage, durable audit delivery, deployment networking and promotion remain separate integration gates. The UI is a private local demonstration, not a production authentication service. Model explanations remain untrusted even when they cite valid evidence.

## Run the demonstrations

Use the repository's existing locked Python 3.12 environment. No new dependency, browser package, asset CDN or build system is required.

```bash
python3 -B scripts/diagnose-infrastructure.py --scenario docker-config --language ar
python3 -B scripts/analyze-demo-expenses.py --period 2026-01 --user demo-alpha
python3 -B scripts/analyze-demo-expenses.py --period 2026-01 --user demo-beta
python3 -B scripts/analyze-demo-expenses.py  # requests a reporting period
python3 -B scripts/serve-demo-agents.py --user demo-alpha --port 8765
```

Open `http://127.0.0.1:8765` on the server's own machine. Stop it with Ctrl+C. Do not expose this service publicly or put a proxy in front of it. The user is selected at startup and cannot be switched by browser data. No credentials need to be supplied for offline operation. Do not enter real data; the UI offers fixed synthetic requests and scenarios only.

Run the agent suite and complete repository gates:

```bash
python3 -B -m unittest discover -s tests/agents -p 'test_*.py'
bash scripts/check.sh
```

## Data and evidence

[CI fixtures](../../demo/fixtures/ci.json) cover archive exporter/driver mismatch, Docker configuration lifecycle and GKE default-pool/version conflict. They are synthetic examples inspired by reviewed failures, not retained operational logs or current cloud state. [Image evidence](../../demo/fixtures/image.json) is invented qualification data, not a registry-digest claim. [Runbook sections](../../demo/fixtures/runbooks.json) are bounded, suggestion-only excerpts created for these demonstrations.

[Expenses](../../demo/fixtures/expenses.json) contain two tenants and two months, no product schema or real account/customer records. For January 2026, demo-alpha totals 24,000 SAR minor units across three expenses; demo-beta totals 9,000 across two. Tool results omit raw tenant IDs and individual rows. Empty months return an explicit zero/count-zero dataset, not a guessed reporting period.

Responses include the reporting period, actual source IDs, deterministic tool facts, sanitized pseudonymous traces and qualification-only governance events. A governance event is not proof that a tool executed successfully; `tool_executions` counts attempted dispatches, and only validated successful results enter `facts`. On a required-control failure, no partial unsafe result is returned and no operation is retried.

See [architecture and limits](architecture.md) and the [decision record](adr-001-bounded-demo-agents.md).
