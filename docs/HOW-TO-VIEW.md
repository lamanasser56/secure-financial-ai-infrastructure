# How to view the platform

The platform has no public address. You reach every page through a private port-forward on your own computer, and
only while the platform is up.

## Start

1. `make up` scales the cluster from 0 to 1 node and deploys the platform. It takes about 2 minutes.
2. In one terminal, run `make port-forward` for the front door: the console (Map, Agents, Onboard, Ops, Break it).
3. In a second terminal, run `make agent-forward A=financial` for the Financial Agent.
4. Optional, in a third terminal: `make agent-forward A=platform-guide` for the Platform Guide.

Use `127.0.0.1`, not `localhost`: each page accepts only its exact local address.

| Page | Address | What it shows |
| --- | --- | --- |
| Console | <http://127.0.0.1:8080/> | **Map** (the cluster drawing, agent health, latest activity), **Agents** (passports and the live check), **Onboard** (the eight guarantees), **Ops** (incident timeline and owner approval), **Break it** (the latest attack-suite results). Click any part to open its explanation. |
| Financial Agent | <http://127.0.0.1:8081/> | Sign in, then **Ask** (the answer, and on the right what the platform did for that question) or **Expenses**. |
| Platform Guide | <http://127.0.0.1:8082/> | Questions about the platform, answered from the documentation bundled into its image at build time. |

## On every page

- **Live** in the header means the console received data in the last minute; **Offline** means it did not. Nothing on
  a screen is sample data: a value is real or the screen says it is not available.
- Every box, line, chip and list row opens an **Explain** drawer (Esc closes it): plain words, how it works, the live
  proof, and what would happen without it. If no live proof exists, the drawer says so.
- The console is English only. Run it locally without a cluster: see `docs/console/design-spec.md`, "Running locally".

## Approving a fix

When a service fails, the operations agent proposes a restart or a bounded scale (a replica count within the registered bounds). Type the owner passphrase,
select **Approve** on the **Ops** screen (it then executes once). An approval is valid once, for that action on that service, for 5 minutes.
If the service changes in between, the platform refuses the action and changes nothing.

## Stop

Stop the port-forwards (Ctrl+C), then run `make down`. It snapshots the database and scales the cluster to 0 nodes.
