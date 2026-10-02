"""Validate the standalone portfolio boundary and parse declarative assets."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATH_PARTS = {"backend", "frontend", "database", "fonts"}
FORBIDDEN_CONTENT = (
    re.compile(r"project-[0-9a-f]{8}-[0-9a-f-]{10,}"),
    re.compile(r"github\.com/[^\s/]+/masar-ai(?:[\s/]|$)", re.IGNORECASE),
    re.compile(r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com"),
    re.compile(r"[a-z0-9-]+/masar-app@sha256:[0-9a-f]{64}"),
)


def main() -> None:
    files = [
        p for p in ROOT.rglob("*")
        if p.is_file() and not {".git", ".venv", "__pycache__"}.intersection(p.parts)
    ]
    assert files, "empty repository"
    for path in files:
        relative = path.relative_to(ROOT)
        assert not FORBIDDEN_PATH_PARTS.intersection(relative.parts), relative
        if path.suffix in {".py", ".md", ".json", ".yaml", ".yml", ".sh"}:
            content = path.read_text(encoding="utf-8")
            for prohibited in FORBIDDEN_CONTENT:
                assert not prohibited.search(content), f"source-specific value in {relative}"
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("$schema") == "https://json-schema.org/draft/2020-12/schema":
                Draft202012Validator.check_schema(data)
        elif path.suffix in {".yaml", ".yml"}:
            docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            assert docs and all(isinstance(doc, dict) for doc in docs), relative
            if path.name == "kustomization.yaml":
                for item in docs[0].get("resources", []):
                    assert (path.parent / item).exists(), f"missing Kustomize resource {item}"

    config = yaml.safe_load((ROOT / "kubernetes/apps/litellm/configmap.yaml").read_text())
    assert "REPLACE_WITH_GCP_PROJECT_ID" in config["data"]["config.yaml"]
    assert "REPLACE_WITH_APPROVED_MODEL" in config["data"]["config.yaml"]
    service_account = yaml.safe_load((ROOT / "kubernetes/apps/litellm/serviceaccount.yaml").read_text())
    assert "iam.gke.io/gcp-service-account" not in service_account["metadata"].get("annotations", {})
    print(f"Validated {len(files)} portfolio files, JSON Schemas, YAML, and source boundary")


if __name__ == "__main__":
    main()
