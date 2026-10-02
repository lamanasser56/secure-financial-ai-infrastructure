#!/usr/bin/env bash
set -euo pipefail

# Install pinned, checksum-verified public scanner binaries into a caller-owned
# temporary directory. This script does not change the repository or PATH.
tool_dir="${1:-}"
[[ -n "$tool_dir" && "$tool_dir" == /* && -d "$tool_dir" ]] || {
  echo 'provide an existing absolute destination directory' >&2
  exit 2
}

fetch() {
  local url="$1" expected="$2" output="$3"
  curl --fail --silent --show-error --location --output "$output" "$url"
  printf '%s  %s\n' "$expected" "$output" | sha256sum --check >/dev/null
}

fetch 'https://github.com/aquasecurity/trivy/releases/download/v0.72.0/trivy_0.72.0_Linux-64bit.tar.gz' \
  'bbb64b9695866ce4a7a8f5c9592002c5961cab378577fa3f8a040df362b9b2ea' "$tool_dir/trivy.tar.gz"
tar -xzf "$tool_dir/trivy.tar.gz" -C "$tool_dir" trivy
fetch 'https://github.com/anchore/syft/releases/download/v1.44.0/syft_1.44.0_linux_amd64.tar.gz' \
  '0e91737aee2b5baf1d255b959630194a302335d848ff97bb07921eb6205b5f5a' "$tool_dir/syft.tar.gz"
tar -xzf "$tool_dir/syft.tar.gz" -C "$tool_dir" syft
fetch 'https://github.com/sigstore/cosign/releases/download/v2.6.2/cosign-linux-amd64' \
  'd437b8f0d30f5dec169337607fcfa0238de1348503e175f1bb5b94330b1ee409' "$tool_dir/cosign"
fetch 'https://github.com/google/osv-scanner/releases/download/v2.4.0/osv-scanner_linux_amd64' \
  '15314940c10d26af9c6649f150b8a47c1262e8fc7e17b1d1029b0e479e8ed8a0' "$tool_dir/osv-scanner"
chmod 0755 "$tool_dir/trivy" "$tool_dir/syft" "$tool_dir/cosign" "$tool_dir/osv-scanner"
echo "Pinned qualification tools installed in $tool_dir"
