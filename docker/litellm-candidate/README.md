# Unpromoted LiteLLM proxy candidate

Final minimal-proxy dependency-closure candidate, not the committed deployment. See
[qualification](../../evaluation/litellm-candidate/qualification.json) and
[identity/gateway preparation](../../docs/agents/identity-and-gateway-preparation.md).
No admin UI or Node toolchain is built. Proxy dependencies remain completely
hash-locked; no selective finding filter or exception is permitted.

Build only on the worker with an explicitly bootstrapped `docker-container`
builder and the recorded immutable BuildKit digest. The
[build script](../../scripts/build-litellm-candidate.sh) requires a new archive
path and fixed source epoch. It never loads, publishes, signs or promotes images.
Review build-input hashes and archive configuration separately from source history.
Reproducibility, import/health/protocol/key/database/network qualification are
separate gates; no registry digest or signature is implied by a local image ID.

Isolated qualification uses nonroot 65532, read-only root, bounded temporary space,
no capabilities, no external network, dummy keys and a local provider stub only.
It does not qualify real credentials, a key database, Gemini or live redaction.
Actual deployment requires separately accepted artifacts, identity, privacy,
gateway/key enforcement, audit and cleanup plans. Presidio authority is unchanged.
