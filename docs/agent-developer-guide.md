# Developer guide: put your agent on the platform

This guide is for engineers on a team that wants to run an AI agent on the Secure AI Agent Platform. You write one
file. The platform validates it and gives your agent its security controls; you do not build them.

The rules behind each step are in the [agent onboarding contract](agent-onboarding-contract.md).

## 1. Write the manifest

Create `platform/agents/<your-agent>/agent.yaml`. The name is 3–22 lowercase letters, digits or hyphens. The smallest
working example is [`platform/agents/hello/agent.yaml`](../platform/agents/hello/agent.yaml):

```yaml
agent: hello
team: platform-examples
description: The smallest possible agent. It greets a user through the platform's model path.
placement: namespace          # your agent gets its own namespace: agent-hello
runtime:
  image: app                  # an agent image that CI built, scanned, signed and pinned
  command: [/usr/local/bin/python3.12, -m, agent_platform.programs.hello_agent]
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
make onboard A=hello
```

The command does one of two things:

- **It refuses the manifest** and gives the reason, for example `tool is not read-only: …` or `model budget: the
  platform total would exceed $10.00/month`. Nothing is generated.
- **It accepts the manifest.** It lists what your agent inherits and writes the generated files to
  `platform/core/kubernetes/agents/` (do not edit them; `make test` fails if they drift from the manifests).

## 3. What your agent inherits

| Control | What the platform generates or enforces |
|---|---|
| Isolation | Namespace `agent-<name>` with Pod Security "restricted", and a quota that allows no load balancers or node ports |
| Network | Default deny. Egress is allowed only to DNS, the redactor and the LiteLLM gateway: never the internet, never a model provider |
| Model access | Its own gateway key with your monthly budget. It calls only the stable alias `secure-financial-chat` |
| Redaction | A redactor client key. Every model call is redacted first; if redaction fails, nothing is sent |
| Workload | Nonroot, read-only root filesystem, no capabilities, no Kubernetes API token, resource limits |
| Supply chain | Only an image that CI signed and attested runs (Binary Authorization) |
| Tools | Only registered, enabled, read-only tools that need no approval |
| Operations | The Security & Operations Agent cannot act on your agent unless it is registered as a target |

`make up` deploys the generated objects. It also creates your agent's keys in the Secret `agent-<name>/agent`
(`agent.json` holds `gateway_key` and `redactor_key`), without rotating any other key.

## 4. Your agent's code

Your program reads `/secrets/agent/agent.json`, listens on its port, and answers `GET /healthz`. For model calls it
must follow the pattern in
[`hello_agent.py`](../platform/core/src/agent_platform/programs/hello_agent.py):

1. Redact the user's text with the redactor client (`RedactorClient` + `DeterministicEmailRedactor`). On failure,
   stop: no model request.
2. Call `http://gateway.platform.svc.cluster.local:4000/v1/chat/completions` with your key and the alias.
3. Accept only a complete reply (`finish_reason` = `stop`) and treat its text as untrusted data.

## 5. How users reach your agent

- **Today: port-forward only.** An onboarded agent has no public endpoint and no route through the front door. Its
  only way in is an IAM-gated `kubectl port-forward` from the owner's laptop to its ClusterIP Service, for example
  `make hello`, which forwards `127.0.0.1:18080` to `agent-hello` and sends one request. Its default-deny ingress
  admits no other pod in the cluster.
- **Future work: front-door routing.** The front door (`apps/app`) would authenticate the user, apply the per-user
  rate limit and budget, and forward the request to the agent's Service. That needs an explicit ingress rule from the
  front door to the agent's namespace (a network change, reviewed as a diff). The Financial Agent rewrite is the first
  candidate.

## 6. Try it

```bash
make up
make hello NAME=Lama            # one greeting = one model request on the hello agent's own key
make down
```

## Known limitations

- **Person names are not redacted.** The redaction entity set has no person-name category.
- **Agent images:** today, onboarded agents run the platform's signed `app` image. Your own agent image would be
  added to the CI image pipeline (scan, sign, attest) and pinned in `platform/clouds/gke/images.json`.
- **Front-door placement:** the Financial Agent still runs inside the front door. Its manifest (`placement:
  front-door`) declares exactly what it has today. The Financial Agent rewrite moves it to its own namespace.
