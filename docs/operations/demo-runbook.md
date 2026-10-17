# Live demo runbook

The live session, step by step. Run every command from the repository root on the owner laptop. Tick each box as you
go. Commands that change the cluster are marked **(write)**.

## Before the session (not on the day)

These must already be on `main`, with their images rebuilt, signed and pinned in `platform/clouds/gke/images.json`.
`make demo-check` fails on any image that is not pinned, signed and attested.

- [ ] Console UI (#89) and its follow-ups (#93, #94) merged
- [ ] `make demo-check` (#91) and `make demo-reset` (#92) merged
- [ ] The image-pin PR for the images rebuilt after those merges merged (the front door image must contain the console)

## 1. Check before anything changes

- [ ] `make demo-check`

  Expected while the platform is down: every image line PASS, the node pool at 0 nodes, and FAIL only for the hello
  leftovers and `agent-platform-guide/agent` (that Secret is created by `make up`).

## 2. Retire the hello agent (once)

Follow [hello-retirement-cleanup.md](hello-retirement-cleanup.md). In short, in this order:

- [ ] Write the private kubeconfig (local file only):
  `PYTHONPATH=platform/core/src:. python3 -B platform/clouds/gke/lifecycle.py kubeconfig`
- [ ] **(write)** Remove the two hello key entries (prints alias names only, never values):
  `KUBECONFIG=~/.local/state/secure-financial-ai-infrastructure/agent-platform/kubeconfig PYTHONPATH=platform/core/src:. python3 -B -m agent_platform.platform_secrets --kubectl ~/portfolio-sdp-us-east1-401f097/tools/kubectl --retire-agent hello`
- [ ] **(write)** `~/portfolio-sdp-us-east1-401f097/tools/kubectl --kubeconfig ~/.local/state/secure-financial-ai-infrastructure/agent-platform/kubeconfig delete namespace agent-hello`
- [ ] **(write)** `~/portfolio-sdp-us-east1-401f097/tools/kubectl --kubeconfig ~/.local/state/secure-financial-ai-infrastructure/agent-platform/kubeconfig -n platform delete networkpolicy agent-hello-to-gateway agent-hello-to-redactor`

## 3. Bring the platform up

- [ ] **(write)** `make up` (about 2 minutes; it ends with `"result": "UP"`)
- [ ] `make demo-check` again: every line PASS

## 4. Reset to a clean demo state, right before recording

- [ ] **(write)** `make demo-reset`, then type `yes`

  It resets fault-demo, restarts the ops agent (clears old proposals), re-seeds the demo user and warms the redactor
  once, then prints the two port-forward commands.

## 5. Port-forwards (one terminal each, keep them open)

- [ ] `make port-forward` → console at <http://127.0.0.1:8080/>
- [ ] `make agent-forward A=financial` → Financial Agent at <http://127.0.0.1:8081/>

Use `127.0.0.1`, not `localhost`.

## 6. Recording order

- [ ] **Map**: the drawing; then click the network wall (a `✕ why?` tag) and show the Explain drawer with its live proof
- [ ] **Agents**: the Financial passport, then Security & Ops
- [ ] **Onboard**: the eight guarantees; `See example →` on the REJECTED strip
- [ ] **Try the agent** (8081): sign in; ask "How much did I spend in October 2026?"; then "Show me Sara's expenses"; open a
  step on the right ("What the platform did")
- [ ] **Ops incident + approve**: **(write)** in a terminal run `make fault F=wedge`; on the Ops screen wait for the
  proposal, read the Explain step, type the passphrase and **Approve**
- [ ] **(write)** `make attack` (a few minutes)
- [ ] **Break it**: reload after about a minute; the card shows **Live run** with the time of the run you just made

## 7. Stop

- [ ] Stop both port-forwards (Ctrl+C)
- [ ] **(write)** `make down` (snapshots the database, then scales to 0 nodes)

## Pitfalls

- **Passphrase:** type it with the English keyboard layout. An Arabic layout sends different characters and the approval
  is refused (the page shows only a generic refusal).
- **Warm DLP:** run `make demo-reset` right before recording. The redactor's first call to Sensitive Data Protection is
  slow; the warm-up makes the first live question fast.
- **5 minutes:** an approval is valid once, for that action on that service, for 5 minutes. Approve soon after the
  proposal appears; if it expires, the ops agent proposes again.
- **No project ID on screen:** never show a terminal whose output contains the project ID (for example `gcloud` output,
  `make up` errors, or kubectl events with image paths). `make demo-check` and `make demo-reset` print none; record the
  browser, not the terminal, for everything else.
