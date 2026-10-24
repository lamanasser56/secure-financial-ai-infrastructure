"""Resolve historical qualification inputs to their archived, exact bytes.

Current runtime locks remain the inputs to all operational qualification gates.
See CLAUDE_HANDOFF_FINAL.md at rc1-live-followup:bed7b0e for the pending
live requalification requirement.
"""

from pathlib import Path


HISTORICAL_LOCK_SHA256 = {
    "requirements-agent-composition.txt": "0f8138170f4db09c943a591d814a5584eb7ab1ae80858981d8606da54a086cd9",
    "requirements-google-sdp-runtime.txt": "c232eac3a105050d5406a7cc80f5aa276c4fbbed52f3e8d5ff7892c548199a29",
    "requirements-litellm-candidate.txt": "71f9c84c122b3ee9ebac6fb00901f5730d888ed3e81c86bbb10d76f3c50c8d0a",
}

HISTORICAL_SOURCE_SHA256 = {
    "requirements-litellm-candidate.in": "baef3535164402bddc9b28fc9411f2f1db41a36c4fc3cb47c77bb826a3dbbc47",
}


def historical_input(root: Path, relative: str, expected_sha256: str) -> Path:
    """Return archived bytes for a qualified input, otherwise the current file.

The hash check on the returned path remains the caller's responsibility. A
changed record hash cannot silently select a different archived lock.
    """
    archives = (
        (HISTORICAL_LOCK_SHA256, "locks"),
        (HISTORICAL_SOURCE_SHA256, "inputs"),
    )
    for hashes, directory in archives:
        if relative not in hashes:
            continue
        if expected_sha256 != hashes[relative]:
            raise AssertionError(f"historical qualification record changed: {relative}")
        return root / "archive/qualification-history" / directory / relative
    return root / relative
