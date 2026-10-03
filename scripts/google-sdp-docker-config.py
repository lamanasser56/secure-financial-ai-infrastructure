#!/usr/bin/env python3
"""Manage only private release authentication; preserve Buildx post-action state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat


REGISTRY = "us-east1-docker.pkg.dev"
DIRECTORIES = {"buildx", "contexts", "cli-plugins"}
FILES = {"config.json", ".token_seed", ".token_seed.lock"}


def fail() -> None:
    raise SystemExit("Unsafe Docker configuration: unexpected path, permissions or configuration")


def inspect(directory: Path) -> bool:
    if not directory.is_absolute() or directory == Path("/"):
        fail()
    for parent in (directory, *directory.parents):
        if parent.is_symlink():
            fail()
    if not directory.exists():
        return False
    root = directory.lstat()
    if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.geteuid() or stat.S_IMODE(root.st_mode) != 0o700:
        fail()
    for entry in directory.iterdir():
        if entry.name not in DIRECTORIES | FILES:
            fail()
        info = entry.lstat()
        if entry.name in DIRECTORIES and not stat.S_ISDIR(info.st_mode):
            fail()
        if entry.name in FILES and not stat.S_ISREG(info.st_mode):
            fail()
    for current, directories, files in os.walk(directory, followlinks=False):
        for name in directories + files:
            info = (Path(current) / name).lstat()
            # Private 0700 root protects metadata that the action creates as
            # 0644/0755. Neither group nor others may modify any descendant.
            if (info.st_uid != os.geteuid() or info.st_mode & 0o022
                    or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
                fail()
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                fail()
    config = directory / "config.json"
    if config.exists():
        if stat.S_IMODE(config.lstat().st_mode) != 0o600:
            fail()
        try:
            value = json.loads(config.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or set(value) != {"auths"}:
                fail()
            auths = value["auths"]
            if not isinstance(auths, dict) or set(auths) - {REGISTRY, "https://" + REGISTRY}:
                fail()
            for entry in auths.values():
                if not isinstance(entry, dict) or set(entry) - {"auth"}:
                    fail()
                if "auth" in entry and not isinstance(entry["auth"], str):
                    fail()
        except (OSError, ValueError):
            fail()
    return True


def manage(operation: str, directory: Path) -> None:
    exists = inspect(directory)
    if operation == "init":
        if not exists:
            # Never repair/delete an existing unexpected directory.
            directory.mkdir(mode=0o700)
        config = directory / "config.json"
        if config.exists():
            value = json.loads(config.read_text(encoding="utf-8"))
            if any(entry.get("auth") for entry in value["auths"].values()):
                fail()
        else:
            # A nonempty auths map suppresses Docker's automatic credential-helper
            # selection. No external store is permitted by inspect().
            fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"auths": {REGISTRY: {}}}, stream)
                stream.write("\n")
        inspect(directory)
    elif operation == "check":
        if not exists or not (directory / "config.json").exists():
            fail()
    elif exists:
        # Remove only the validated regular authentication file. Buildx, contexts,
        # plugin and token-seed metadata remain available for the action's post.
        (directory / "config.json").unlink(missing_ok=True)
        inspect(directory)
    print("PASS: private Docker configuration " + operation + "; Buildx state preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("init", "check", "clear-auth"))
    parser.add_argument("directory", type=Path)
    arguments = parser.parse_args()
    manage(arguments.operation, arguments.directory)
