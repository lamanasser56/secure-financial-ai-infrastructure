"""Select the qualified source S for a disposable assessment and record the harness.

The product, including every overlay file whose output is applied to the
assessment cluster, must equal S. Only the orchestration, waiting, verification
and evidence code in assessment_overlay/ may change after S, in commits only.
The bundle itself is rendered by S's own renderer from a detached worktree.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
# Overlay files that render, stage or are embedded in the applied bundle.
DEPLOYED_CONTENT = frozenset('assessment_overlay/' + name for name in (
    'render_live_bundle.py', 'stage_live_bundle.py',
    'patch_gateway_stub.py', 'patch_ops_stub.py', 'patch_redactor_bundle.py',
    'provider_stub.py', 'redactor_server.py', 'ops_server_assessment.py',
    'seed_sdp.py', 'sdp_guard.py'))


HARNESS = 'assessment_overlay/'
RELEASE_LOCK = 'platform/clouds/gke/release-rc1.lock.json'


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout


def checkout_changes(root=ROOT):
    """Paths that differ from HEAD: staged, unstaged, untracked, or hidden from status."""
    changed = set(git(root, 'diff', '--name-only', '--no-renames', 'HEAD').splitlines())
    # Only the repository's own .gitignore files may hide a file, not a personal exclude.
    changed |= set(git(root, 'ls-files', '--others', '--exclude-per-directory=.gitignore').splitlines())
    # assume-unchanged (lower-case tag) and skip-worktree (S) entries hide local edits.
    changed |= {line[2:] for line in git(root, 'ls-files', '-v').splitlines()
                if line[:1].islower() or line[:1] == 'S'}
    return sorted(changed)


def assessed_path(path):
    """Paths that may differ from S: orchestration, waiting, verification and evidence."""
    if path in DEPLOYED_CONTENT:
        return False
    return path == RELEASE_LOCK or path.startswith('docs/evidence/') or path.startswith(HARNESS)


def selected_source(lock, root=ROOT):
    """Return S when this checkout runs S's product exactly.

    Everything outside assessment_overlay/ must equal S, except the release lock
    and docs/evidence/; so must the overlay files that produce what is applied
    to the assessment cluster (DEPLOYED_CONTENT). The rest of the harness may
    change after S, but only in commits: an uncommitted or untracked change
    anywhere refuses the session, so a local edit can never pass as the
    committed harness or as S.
    """
    source = lock.get('source_commit')
    if (lock.get('schema_version') != 2 or lock.get('runtime_contract') != 'trusted-boundaries-v2'
            or not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{40}', source)):
        raise ValueError('current qualified image lock required')
    exists = subprocess.run(['git', 'cat-file', '-e', source + '^{commit}'], cwd=root,
                            capture_output=True, check=False)
    if exists.returncode:
        raise ValueError('selected source commit unavailable')
    if checkout_changes(root):
        raise ValueError('assessment checkout has uncommitted or untracked changes')
    # --no-renames lists both sides, so moving product code into the harness is refused.
    changed = git(root, 'diff', '--name-only', '--no-renames', source, 'HEAD').splitlines()
    if any(not assessed_path(path) for path in changed):
        raise ValueError('assessment source differs from qualified release')
    return source


def harness_record(source, root=ROOT):
    """The committed harness that runs against S, and its S..HEAD diff."""
    diff = git(root, 'diff', '--no-renames', '--binary', source, 'HEAD', '--', HARNESS)
    return {
        'harness_commit': git(root, 'rev-parse', 'HEAD').strip(),
        'harness_changed_files': git(root, 'diff', '--name-only', '--no-renames', source, 'HEAD',
                                     '--', HARNESS).splitlines(),
        'harness_diff_sha256': hashlib.sha256(diff.encode()).hexdigest(),
    }, diff


def assert_harness_unchanged(manifest, root=ROOT):
    """Each operator step runs the exact clean harness commit the session recorded."""
    if (git(root, 'rev-parse', 'HEAD').strip() != manifest.get('harness_commit')
            or checkout_changes(root)):
        raise SystemExit('assessment:harness_checkout_changed_since_session')


@contextmanager
def source_tree(source, root=ROOT):
    """A private detached worktree at S, removed afterwards."""
    with tempfile.TemporaryDirectory(prefix='assessment-source-') as directory:
        tree = Path(directory) / 'source'
        git(root, 'worktree', 'add', '--detach', '--quiet', str(tree), source)
        try:
            if git(tree, 'rev-parse', 'HEAD').strip() != source:
                raise ValueError('assessment source worktree mismatch')
            yield tree
        finally:
            git(root, 'worktree', 'remove', '--force', str(tree))
