#!/usr/bin/env python3
"""Offline exact diagnostic profile plus the inherited security contract.

No resource application, cloud access or SDK client construction. Scope/attempt
annotations document the fixed harness behavior; the qualified image and exact
arguments enforce it. This validator does not qualify an arbitrary image digest.
"""

import copy
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "google-sdp-evaluation-controls.yaml",
    "google-sdp-evaluation-job.yaml",
    "google-sdp-egress-preflight.yaml",
    "networklogging.yaml",
)
ACKNOWLEDGEMENTS = [
    {
        "name": "PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK",
        "value": "I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY",
    },
    {
        "name": "PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK",
        "value": "I_ACKNOWLEDGE_CONTEXT_001_ONLY_TWO_ATTEMPTS",
    },
]


def read_yaml(path):
    """Bound and reject special files before parsing trusted render output."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
        raise ValueError
    documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    if not documents or any(type(document) is not dict for document in documents):
        raise ValueError
    return documents


def validate(path):
    path = Path(path)
    documents = read_yaml(path)
    directory = path.parent
    # Side files and combined output must agree; no divergent apply subjects.
    side = {name: read_yaml(directory / name) for name in FILES}
    jobs = [document for document in documents if document.get("kind") == "Job"]
    maps = [document for document in documents if document.get("kind") == "ConfigMap"]
    if len(documents) != 8 or len(jobs) != 1 or len(maps) != 1:
        raise ValueError
    job = jobs[0]
    if side[FILES[1]] != [job] or side[FILES[0]] != [
        document for document in documents if document["kind"] != "Job"
    ]:
        raise ValueError
    if maps[0]["data"] != {
        "region": "us-east1",
        "endpoint": "dlp.us-east1.rep.googleapis.com",
        "synthetic_corpus_path": "/app/evaluation/google-sdp-context/corpus.json",
    }:
        raise ValueError
    container = job["spec"]["template"]["spec"]["containers"][0]
    match = re.fullmatch(
        r"us-east1-docker\.pkg\.dev/([a-z][a-z0-9-]{4,28}[a-z0-9])/sdp-evaluation-images/google-sdp-context-diagnostic@sha256:[0-9a-f]{64}",
        container["image"],
    )
    if match is None:
        raise ValueError
    # Exact equivalence rejects command, environment, selector, volume and resource
    # additions, as well as unsuspension, retries and a full-campaign entry point.
    expected = yaml.safe_load(
        (ROOT / "kubernetes/apps/google-sdp-evaluation/job.yaml").read_text()
    )
    expected["metadata"]["name"] = "google-sdp-context-diagnostic"
    expected["metadata"]["annotations"] = {
        "portfolio.example/evaluation-scope": "context-001-only",
        "portfolio.example/content-attempt-limit": "2",
    }
    expected["spec"]["activeDeadlineSeconds"] = 120
    expected_container = expected["spec"]["template"]["spec"]["containers"][0]
    expected_container["image"] = container["image"]
    expected_container["args"] = ["--live", "--diagnostic-first-case"]
    expected_container["env"] = [
        {"name": "PORTFOLIO_GOOGLE_SDP_PROJECT_ID", "value": match.group(1)},
        *copy.deepcopy(ACKNOWLEDGEMENTS),
    ]
    if job != expected:
        raise ValueError
    # Preserve the original security validator as the authoritative reusable
    # check. Normalize only the enumerated diagnostic profile differences.
    job["metadata"]["name"] = "google-sdp-evaluation"
    job["metadata"].pop("annotations")
    job["spec"]["activeDeadlineSeconds"] = 900
    container["args"] = ["--live"]
    container["env"] = [
        {"name": "PORTFOLIO_GOOGLE_SDP_PROJECT_ID", "value": match.group(1)},
        {
            "name": "PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK",
            "value": "I_ACKNOWLEDGE_SYNTHETIC_ONLY_GOOGLE_SDP_EVALUATION",
        },
    ]
    maps[0]["data"]["synthetic_corpus_path"] = "/app/evaluation/google-sdp/corpus.json"
    with tempfile.TemporaryDirectory(prefix="portfolio-diagnostic-validation-") as temporary:
        target = Path(temporary) / "validation.yaml"
        target.write_text(yaml.safe_dump_all(documents, sort_keys=False))
        (target.parent / FILES[0]).write_text(
            yaml.safe_dump_all(
                [document for document in documents if document["kind"] != "Job"],
                sort_keys=False,
            )
        )
        (target.parent / FILES[1]).write_text(yaml.safe_dump(job, sort_keys=False))
        for name in FILES[2:]:
            shutil.copyfile(directory / name, target.parent / name)
        subprocess.run(
            ["bash", str(ROOT / "scripts/validate-google-sdp-deployment.sh"), str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError
        validate(sys.argv[1])
    except Exception:
        raise SystemExit("diagnostic deployment contract rejected") from None
    print("PASS: context-001-only diagnostic and inherited deployment security contract")
