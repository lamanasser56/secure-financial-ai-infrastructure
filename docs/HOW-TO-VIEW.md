# How to view the platform

The platform has no public address. You reach every page through a private port-forward on your own computer, and
only while the platform is up.

## Start

1. `make up` scales the cluster from 0 to 1 node and deploys the platform. It takes about 2 minutes.
2. In one terminal, run `make port-forward` for the front door: About and Security & Operations.
3. In a second terminal, run `make agent-forward A=financial` for the Financial Agent.

Use `127.0.0.1`, not `localhost`: each page accepts only its exact local address.

| Page | Address | What it shows |
| --- | --- | --- |
| About | <http://127.0.0.1:8080/> | What the platform is, the agents running on it, how a question is answered, how a problem is fixed, and the protections every agent inherits. |
| Security & Operations | <http://127.0.0.1:8080/operations.html> | **Operations** tab: the live status board, the incident for the selected service (steps, AI explanation, proposed action, owner approval, verified outcome), pending approvals, policy denials and the timeline. **Security** tab: the live checks and the attack-suite checks. |
| Financial Agent | <http://127.0.0.1:8081/> | Sign in, then **Ask the agent** (answer, how we know, privacy check) or **My expenses**. |

## On every page

- **EN | ع** switches the language. Arabic pages read right to left and use Western digits (0–9) and Gregorian dates
  such as "12 أكتوبر 2026".
- **?** opens the guided tour. It also opens by itself on your first visit; "seen" is remembered in the browser.
- **Technical details** at the bottom of a card shows the raw response.

## Approving a fix

When a service fails, the operations agent proposes a restart or a bounded resize. Type the owner passphrase,
select **Approve**, then **Execute once**. An approval is valid once, for that action on that service, for 5 minutes.
If the service changes in between, the platform refuses the action and changes nothing.

## Stop

Stop both port-forwards (Ctrl+C), then run `make down`. It snapshots the database and scales the cluster to 0 nodes.
