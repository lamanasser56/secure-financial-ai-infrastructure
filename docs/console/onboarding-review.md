# Console onboarding review

The Onboard screen is read-only: it reviews **existing** agents from the selected release. Refresh observations
performs GET requests. It does not register an agent, generate configuration, create keys or deploy workloads.
The Manifest summary is a presentation of selected fields, **not an applicable agent.yaml**.

Each check describes one limited fact. **Observed** means a fact was read from its stated source; **Inferred** is
a conclusion from observations; **Declared** means configuration only; **Failing** means an observed contradiction.
The passport and Map show partial coverage. A ready workload gives an image-admission inference, not a
cryptographic signature verification. `make demo-check` performs release signature and attestation verification.
Reading a default-deny policy does not independently test every packet path. A recent masking event does not
establish coverage of all requests. The masking drawer lists supported patterns and explicitly excludes person
names and passport numbers.

## Owner workflow

Write a manifest under `platform/agents/<name>/agent.yaml` following the current
[onboarding contract](../agent-onboarding-contract.md). The current validator checks the closed schema, approved
images, per-agent and platform budgets, and registered read-only tools. The reviewed Financial data route uses
the trusted frontdoor and data broker; workers do not hold database credentials. Ops observes and proposes;
the separate approval executor verifies authorization and owns the declared mutation rights.

```sh
make onboard-check F=platform/agents/<name>/agent.yaml
make onboard A=<name>
```

The first command validates only; the second generates configuration. Review and commit the generated
configuration before deploying a selected release with `make up`. Generation alone is not a deployment or a
release qualification.

The shipped [rejected example](../examples/rejected-agent/agent.yaml) is intentionally invalid:

```sh
make onboard-check F=docs/examples/rejected-agent/agent.yaml
```

Expected output contains these five current rule messages; the checker exits **2**, `make` exits nonzero, and
nothing is generated. Three requested capabilities trigger five rules; the two budget checks and two tool checks
are independent rules about the same offending inputs.

```text
manifest: not allowed: egress
model.budget_usd_month: a number of dollars above 0 and at most 5.00
model budget: the platform total would exceed $10.00/month
tool is not read-only: delete_expenses
tool name looks like a write: delete_expenses
```

## Open the console and agents

After the final deployment is ready, keep these commands running in separate terminals from the owner machine:

```sh
make port-forward
make agent-forward A=financial
make agent-forward A=platform-guide
```

| Screen | Loopback URL | Forwarded workload |
| --- | --- | --- |
| Console | `http://127.0.0.1:8080/` | `apps/app` |
| Financial Agent | `http://127.0.0.1:8081/` | `apps/financial-frontdoor` (trusted login/data boundary) |
| Platform Guide | `http://127.0.0.1:8082/` | `agent-platform-guide/agent` |

The passport's Try link opens the declared agent port and states the required command. Financial's passport link
returns to Console port 8080. These are the supported local ports; no separate custom-port override is offered.
Loopback forwarding does not create a public endpoint. The Financial worker is not exposed directly.
