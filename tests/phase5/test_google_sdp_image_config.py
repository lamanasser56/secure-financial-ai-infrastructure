"""Portable image identity checks without Docker, registry access or extraction."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("image_config_id", ROOT / "scripts/google-sdp-image-config-id.py")
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


def archive(path, *, classic=False, mutation=None):
    config = {"architecture": "amd64", "os": "linux", "created": "1970-01-01T00:00:00Z", "config": {"User": "65532:65532"}}
    if mutation == "architecture":
        config["architecture"] = "arm64"
    elif mutation == "root":
        config["config"]["User"] = "0:0"
    elif mutation == "timestamp":
        config["created"] = "2026-10-03T00:00:00Z"
    raw = json.dumps(config).encode()
    digest = hashlib.sha256(raw).hexdigest()
    name = digest + ".json" if classic else "blobs/sha256/" + digest
    referenced = "../" + name if mutation == "path" else name
    if mutation == "digest":
        referenced = "blobs/sha256/" + "0" * 64
    manifest = [{"Config": referenced, "Layers": [], "RepoTags": ["synthetic:fixture"]}]
    if mutation == "multiple_images":
        manifest *= 2
    with tarfile.open(path, "w") as target:
        for member_name, payload in (("manifest.json", json.dumps(manifest).encode()), (name, raw)):
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            target.addfile(info, io.BytesIO(payload))
            if mutation == "duplicate" and member_name == name:
                target.addfile(info, io.BytesIO(payload))
    return "sha256:" + digest


class ImageConfigIdentityTests(unittest.TestCase):
    def test_classic_and_containerd_archives_use_the_same_config_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "image.tar"
            first = archive(path)
            self.assertEqual(reader.image_config_digest(path), first)
            second = archive(path, classic=True)
            self.assertEqual(reader.image_config_digest(path), second)
            self.assertEqual(first, second)

    def test_invalid_or_ambiguous_archives_are_rejected(self):
        for mutation in ("path", "digest", "multiple_images", "duplicate", "architecture", "root", "timestamp"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "image.tar"
                archive(path, mutation=mutation)
                with self.assertRaises(ValueError):
                    reader.image_config_digest(path)


if __name__ == "__main__":
    unittest.main()
