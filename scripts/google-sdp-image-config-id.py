#!/usr/bin/env python3
"""Read the exact evaluation image configuration digest from a Docker archive.

Docker's .Id can be a manifest digest with the containerd image store. Reading
the configuration bytes avoids using that store-specific identifier as a
cross-runner reproducibility or post-push comparison. Nothing is extracted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def image_config_digest(path: Path) -> str:
    with tarfile.open(path, "r:*") as archive:
        members = archive.getmembers()

        def read(name):
            matches = [member for member in members if member.name == name]
            if len(matches) != 1 or not matches[0].isfile() or not 0 < matches[0].size <= 1024 * 1024:
                raise ValueError
            return archive.extractfile(matches[0]).read()

        manifest = json.loads(read("manifest.json"), object_pairs_hook=_unique)
        if type(manifest) is not list or len(manifest) != 1:
            raise ValueError
        name = manifest[0]["Config"]
        match = re.fullmatch(r"(?:blobs/sha256/([0-9a-f]{64})|([0-9a-f]{64})\.json)", name)
        if match is None:
            raise ValueError
        raw = read(name)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != (match.group(1) or match.group(2)):
            raise ValueError
        config = json.loads(raw, object_pairs_hook=_unique)
        if config["architecture"] != "amd64" or config["os"] != "linux":
            raise ValueError
        if config["config"]["User"] != "65532:65532":
            raise ValueError
        if config["created"] not in {"1970-01-01T00:00:00Z", "1970-01-01T00:00:00.000000000Z"}:
            raise ValueError
        return "sha256:" + digest


def main():
    if len(sys.argv) != 2:
        print("usage: google-sdp-image-config-id.py DOCKER_ARCHIVE", file=sys.stderr)
        return 2
    try:
        digest = image_config_digest(Path(sys.argv[1]))
    except Exception:
        print("image:invalid_archive", file=sys.stderr)
        return 2
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
