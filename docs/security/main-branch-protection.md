# Main branch protection

The owner applies these settings in the GitHub UI. CI cannot apply them, and no workflow token has
administration rights. From the day they apply, every change reaches `main` through a pull request.

## Settings

Path: **Settings → Rules → Rulesets → New ruleset → New branch ruleset**.

| Setting | Value |
| --- | --- |
| Ruleset name | `protect-main` |
| Enforcement status | Active |
| Bypass list | Empty. Nobody bypasses, including administrators. |
| Target branches | Include default branch (`main`) |
| Restrict deletions | On |
| Block force pushes | On |
| Require a pull request before merging | On |
| Required approvals | 0 (single-maintainer repository) |
| Dismiss stale approvals, require review from Code Owners, require approval of the most recent push | Off |
| Require conversation resolution | Off |
| Allowed merge methods | Rebase (linear history) |
| Require status checks to pass | On |
| Require branches to be up to date before merging | On |
| Required checks (source: GitHub Actions) | `checks`, `agents`, `gitleaks`, `google-sdp-offline-evaluation`, `qualification` |

The `gitleaks` check exists only after the pull request that adds the `gitleaks` job is merged. Add it
to the list after that first run. A required check that has never run blocks every pull request.

## Equivalent API request (optional)

`gh api --method POST repos/lamanasser56/secure-financial-ai-infrastructure/rulesets --input main-ruleset.json`,
with this body:

```json
{
  "name": "protect-main",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": false,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": false,
      "allowed_merge_methods": ["rebase"]}},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [
        {"context": "checks", "integration_id": 15368},
        {"context": "agents", "integration_id": 15368},
        {"context": "gitleaks", "integration_id": 15368},
        {"context": "google-sdp-offline-evaluation", "integration_id": 15368},
        {"context": "qualification", "integration_id": 15368}]}}
  ]
}
```

`15368` is the GitHub Actions app ID. It pins each check to Actions, so another app cannot report it.

## What signing depends on

`agent-platform-images.yml` runs only after `Validate infrastructure portfolio` has passed on a push to
`main`. It builds and signs that exact commit, never the newest one. A manual dispatch is also refused
unless the commit already has a successful CI run on `main`. Images are then signed only for reviewed,
CI-green code, and the Binary Authorization admission check admits only signed images.

## Verification after applying

- `gh api repos/lamanasser56/secure-financial-ai-infrastructure/rules/branches/main` lists the
  `deletion`, `non_fast_forward`, `pull_request` and `required_status_checks` rules.
- `git push origin HEAD:main` from a local commit is rejected.
