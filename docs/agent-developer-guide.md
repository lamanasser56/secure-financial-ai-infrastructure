# Developer guide: put your agent on the platform

This guide is for engineers on a team that wants to run an AI agent on the Secure AI Agent Platform. You write one
file. The platform validates it and gives your agent its security controls; you do not build them.

The rules behind each step are in the [agent onboarding contract](agent-onboarding-contract.md).

## 1. Write the manifest

Create `platform/agents/<your-agent>/agent.yaml`. The name is 3–22 lowercase letters, digits or hyphens. The working
example is [`platform/agents/financial/agent.yaml`](../platform/agents/financial/agent.yaml). The smallest shape the
platform accepts (no tools, no data) looks like this:

```yaml
agent: my-agent
team: my-team
description: What the agent does, in one sentence.
placement: namespace          # your agent gets its own namespace: agent-my-agent
runtime:
  image: my-agent             # an agent image that CI built, scanned, signed and pinned (images.json)
  command: [/usr/local/bin/python3.12, -m, my_agent.server]
  port: 8080
  replicas: 1
  resources: {cpu: 50m, memory: 96Mi}
model:
  budget_usd_month: 0.5       # your own gateway key; the platform total stays $10/month
redaction: required
tools: []                     # registered, read-only tools only
data: none                    # or read access through an existing role under row-level security
```

These are the only fields. Anything else is refused, including:

- egress rules;
- privileges or host access;
- a Service type;
- RBAC;
- a model name or provider key;
- turning redaction off.

## 2. Run `make onboard`

```bash
make onboard A=my-agent
```

The command does one of two things:

- **It refuses the manifest** and prints one line for every rule it breaks, for example `tool is not read-only: …`
  or `model budget: the platform total would exceed $10.00/month`. Nothing is generated. `make onboard-check
  F=docs/examples/rejected-agent/agent.yaml` shows this for any manifest file without touching the repository.
- **It accepts the manifest.** It lists what your agent inherits and writes the generated files to
  `platform/core/kubernetes/agents/` (do not edit them; `make test` fails if they drift from the manifests).

## 3. What your agent inherits

| Control | What the platform generates or enforces |
|---|---|
| Isolation | Namespace `agent-<name>` with Pod Security "restricted", and a quota that allows no load balancers or node ports |
| Network | Default deny. Egress is allowed only to DNS, the redactor and the LiteLLM gateway: never the internet, never a model provider |
| Model access | Its own gateway key with your monthly budget. It calls only the stable alias `secure-financial-chat` |
| Redaction | A redactor client key. The platform client libraries redact every model call first; if redaction fails, nothing is sent. The gateway does not check this, so your code must use the client and never call the gateway with unredacted text ([known limitations](security/known-limitations.md)) |
| Workload | Nonroot, read-only root filesystem, no capabilities, no Kubernetes API token, resource limits |
| Supply chain | Only an image that CI signed and attested runs (Binary Authorization) |
| Tools | Only registered, enabled, read-only tools that need no approval |
| Operations | The Security & Operations Agent cannot act on your agent unless it is registered as a target |

`make up` deploys the generated objects. It also creates your agent's keys in the Secret `agent-<name>/agent`
(`agent.json` holds `gateway_key` and `redactor_key`), without rotating any other key.

## 4. Your agent's code

Your program reads `/secrets/agent/agent.json`, listens on its port, and answers `GET /healthz`. For model calls it
must follow the pattern in the Financial Agent
([`agent.py`](../platform/agents/financial/finance_agent/agent.py)):

1. Redact the user's text with the redactor client (`RedactorClient` + `DeterministicEmailRedactor`). On failure,
   stop: no model request.
2. Call `http://gateway.platform.svc.cluster.local:4000/v1/chat/completions` with your key and the alias.
3. Accept only a complete reply (`finish_reason` = `stop`) and treat its text as untrusted data.

## 5. How users reach your agent

- **Today: port-forward only.** An onboarded agent has no public endpoint and no route through the front door. Its
  only way in is an IAM-gated `kubectl port-forward` from the owner's laptop to its ClusterIP Service, for example
  `make agent-forward A=<agent>`, which forwards the agent's port to `127.0.0.1`. Its default-deny ingress admits no
  other pod in the cluster.
- **Future work: front-door routing.** The front door (`apps/app`) would authenticate the user, apply the per-user
  rate limit and budget, and forward the request to the agent's Service. That needs an explicit ingress rule from the
  front door to the agent's namespace (a network change, reviewed as a diff). Not built: the Financial Agent, the
  first candidate, is reached by port-forward like every onboarded agent.

## 6. Try it

```bash
make up
make agent-forward A=my-agent   # then open http://127.0.0.1:<port>/
make down
```

## 7. A real example: the Financial Agent

[`platform/agents/financial/agent.yaml`](../platform/agents/financial/agent.yaml) is tenant #1:

- **Image:** its own image (`platform/agents/financial/Dockerfile`), built, scanned, signed and attested by the same CI
  pipeline, and pinned in `images.json` as `agent-financial`.
- **Data:** `finance` under per-user row-level security. Its tools read through a read-only role; its web API adds
  the signed-in user's own rows. The platform creates the roles, the network path to Postgres (only because data is
  declared), and the users.
- **Users:** three local users (lama, sara, omar) with argon2id hashes. `make up` writes their passwords once to the
  owner's private state (`financial-users.json`, mode 0600); they are never printed or committed.
- **Access:** `make agent-forward A=financial`, then open `http://127.0.0.1:8081/`.

## Known limitations

- **Person names are not redacted.** The redaction entity set has no person-name category.
- **Agent images:** the Financial Agent shows the pattern for your own image (a Dockerfile, one line in the CI image
  matrix, a pin in `platform/clouds/gke/images.json`).
- **Retired front-door agent:** the earlier, qualified Financial Agent in the front door is retired from the product
  (gateway budget 0, not composed). Its code and requalification evidence stay as the qualified reference.
