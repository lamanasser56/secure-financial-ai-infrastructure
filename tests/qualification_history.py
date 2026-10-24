"""Resolve only historical qualification locks to their archived, exact bytes.

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


def historical_input(root: Path, relative: str, expected_sha256: str) -> Path:
    """Return archived bytes for a qualified lock, otherwise the current file.

The hash check on the returned path remains the caller's responsibility. A
changed record hash cannot silently select a different archived lock.
    """
    if relative in HISTORICAL_LOCK_SHA256:
        if expected_sha256 != HISTORICAL_LOCK_SHA256[relative]:
            raise AssertionError(f"historical lock record changed: {relative}")
        return root / "archive/qualification-history/locks" / relative
    return root / relative
