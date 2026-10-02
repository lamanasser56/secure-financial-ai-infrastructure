#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

pass() {
  printf 'PASS: %s\n' "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required lint command is unavailable: $1"
}

((BASH_VERSINFO[0] >= 4)) \
  || fail 'Bash 4 or newer is required for deterministic array handling'

require_command actionlint
require_command find
require_command git
require_command pymarkdown
require_command shellcheck
require_command sort
require_command yamllint

repository_root="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || fail 'run this script from a Git working tree'
cd "$repository_root"

printf 'Lint tool versions:\n'
actionlint -version
pymarkdown version
shellcheck --version
yamllint --version

mapfile -t markdown_files < <(
  find . -path './.git' -prune -o -type f -name '*.md' -print | LC_ALL=C sort
)
((${#markdown_files[@]} > 0)) || fail 'no Markdown files were found'
pymarkdown --strict-config --config .pymarkdown.json scan "${markdown_files[@]}" \
  || fail 'Markdown linting failed'
pass "Markdown linting passed for ${#markdown_files[@]} files"

mapfile -t yaml_files < <(
  find . -path './.git' -prune -o -type f \
    \( -name '*.yaml' -o -name '*.yml' \) -print | LC_ALL=C sort
)
((${#yaml_files[@]} > 0)) || fail 'no YAML files were found'
yamllint --strict --config-file .yamllint.yaml "${yaml_files[@]}" \
  || fail 'YAML linting failed'
pass "YAML linting passed for ${#yaml_files[@]} files"

mapfile -t workflow_files < <(
  find .github/workflows -type f \( -name '*.yaml' -o -name '*.yml' \) \
    -print | LC_ALL=C sort
)
((${#workflow_files[@]} > 0)) || fail 'no GitHub Actions workflow files were found'
actionlint -no-color "${workflow_files[@]}" \
  || fail 'GitHub Actions linting failed'
pass "GitHub Actions linting passed for ${#workflow_files[@]} files"

mapfile -t shell_files < <(
  find . -path './.git' -prune -o -type f -name '*.sh' -print | LC_ALL=C sort
)
((${#shell_files[@]} > 0)) || fail 'no Bash files were found'
shellcheck --rcfile .shellcheckrc --shell bash "${shell_files[@]}" \
  || fail 'Bash linting failed'
pass "Bash linting passed for ${#shell_files[@]} files"

pass 'repository linting completed'
