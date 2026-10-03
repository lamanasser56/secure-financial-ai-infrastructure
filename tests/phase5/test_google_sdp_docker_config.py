"""Filesystem and lifecycle regressions; real Docker exercise runs on the worker."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANAGER = ROOT / "scripts/google-sdp-docker-config.py"


class DockerConfigTests(unittest.TestCase):
    def run_manager(self, operation, path):
        return subprocess.run(["python3", "-B", str(MANAGER), operation, str(path)],
                              capture_output=True, text=True, check=False)

    def test_absent_and_buildx_populated_directory_keep_metadata_after_auth_cleanup(self):
        for populated in (False, True):
            with self.subTest(populated=populated), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary) / "docker-config"
                if populated:
                    directory.mkdir(mode=0o700)
                    (directory / "buildx").mkdir(mode=0o700)
                    (directory / "buildx/current").write_text("synthetic-builder-state")
                    (directory / "buildx/current").chmod(0o600)
                self.assertEqual(self.run_manager("init", directory).returncode, 0)
                self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
                config = directory / "config.json"
                self.assertEqual(config.stat().st_mode & 0o777, 0o600)
                config.write_text(json.dumps({"auths": {"us-east1-docker.pkg.dev": {"auth": "dummy-only"}}}))
                self.assertEqual(self.run_manager("check", directory).returncode, 0)
                self.assertNotEqual(self.run_manager("init", directory).returncode, 0)
                for _ in range(2):
                    self.assertEqual(self.run_manager("clear-auth", directory).returncode, 0)
                    self.assertFalse(config.exists())
                if populated:
                    self.assertEqual((directory / "buildx/current").read_text(), "synthetic-builder-state")

    def test_unsafe_paths_fail_without_deletion_or_content_output(self):
        for mutation in ("root_symlink", "ancestor_symlink", "public_root", "unknown_file",
                         "nested_symlink", "writable_metadata", "config_symlink", "config_public",
                         "credential_helper", "unexpected_registry", "hardlink", "fifo"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                parent = Path(temporary)
                directory = parent / "docker-config"
                directory.mkdir(mode=0o700)
                self.assertEqual(self.run_manager("init", directory).returncode, 0)
                config = directory / "config.json"
                sentinel = parent / "keep"
                sentinel.write_text("PRIVATE_SENTINEL_DO_NOT_PRINT")
                if mutation == "root_symlink":
                    alias = parent / "alias"
                    alias.symlink_to(directory)
                    directory = alias
                elif mutation == "ancestor_symlink":
                    alias = parent / "alias"
                    alias.symlink_to(parent)
                    directory = alias / directory.name
                elif mutation == "public_root":
                    directory.chmod(0o755)
                elif mutation == "unknown_file":
                    (directory / "unexpected").write_text("keep")
                elif mutation == "nested_symlink":
                    (directory / "buildx").mkdir(mode=0o700)
                    (directory / "buildx/alias").symlink_to(sentinel)
                elif mutation == "writable_metadata":
                    (directory / "buildx").mkdir(mode=0o777)
                    (directory / "buildx").chmod(0o777)
                elif mutation == "config_symlink":
                    config.unlink()
                    config.symlink_to(sentinel)
                elif mutation == "config_public":
                    config.chmod(0o644)
                elif mutation == "credential_helper":
                    config.write_text(json.dumps({"auths": {}, "credsStore": "unexpected"}))
                elif mutation == "unexpected_registry":
                    config.write_text(json.dumps({"auths": {"example.com": {}}}))
                elif mutation == "hardlink":
                    os.link(config, directory / ".token_seed")
                else:
                    os.mkfifo(directory / ".token_seed")
                for operation in ("init", "check", "clear-auth"):
                    result = self.run_manager(operation, directory)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn(sentinel.read_text(), result.stdout + result.stderr)
                    self.assertTrue(config.exists())
                self.assertTrue(sentinel.exists())

    def test_workflow_initializes_before_buildx_and_preserves_post_cleanup_state(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/release-google-sdp-evaluation.yml").read_text())
        steps = workflow["jobs"]["publish"]["steps"]
        initial = next(i for i, step in enumerate(steps) if 'google-sdp-docker-config.py init' in step.get("run", ""))
        buildx = next(i for i, step in enumerate(steps) if step.get("id") == "buildx")
        login = next(step for step in steps if "docker login" in step.get("run", ""))
        self.assertLess(initial, buildx)
        self.assertNotEqual(steps[buildx]["with"].get("cleanup"), False)
        self.assertIn('--password-stdin', login["run"])
        self.assertEqual(login["run"].count('google-sdp-docker-config.py check'), 2)
        cleanup = steps[-1]
        self.assertEqual(cleanup["if"], "always()")
        self.assertIn('google-sdp-docker-config.py clear-auth', cleanup["run"])
        self.assertNotIn('rm -rf', cleanup["run"])
        self.assertNotIn('mkdir -m 700 "$DOCKER_CONFIG"', login["run"])


if __name__ == "__main__":
    unittest.main()
