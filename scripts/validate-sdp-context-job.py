#!/usr/bin/env python3
"""Reuse the established deployment validator after checking context-only differences.

No cloud access or application of resources. Normalization is in memory/private
temporary storage solely to reuse the original immutable security assertions.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import shutil

import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate(path):
    documents = list(yaml.safe_load_all(Path(path).read_text()))
    jobs = [v for v in documents if v.get("kind") == "Job"]
    if len(jobs) != 1:
        raise ValueError
    job = jobs[0]
    directory = Path(path).parent
    if (
        yaml.safe_load((directory / "google-sdp-evaluation-job.yaml").read_text())
        != job
    ):
        raise ValueError
    if list(
        yaml.safe_load_all(
            (directory / "google-sdp-evaluation-controls.yaml").read_text()
        )
    ) != [v for v in documents if v["kind"] != "Job"]:
        raise ValueError
    maps = [v for v in documents if v.get("kind") == "ConfigMap"]
    if len(maps) != 1 or maps[0]["data"] != {
        "region": "us-east1",
        "endpoint": "dlp.us-east1.rep.googleapis.com",
        "synthetic_corpus_path": "/app/evaluation/google-sdp-context/corpus.json",
    }:
        raise ValueError
    if job["metadata"]["name"] != "google-sdp-context-evaluation":
        raise ValueError
    c = job["spec"]["template"]["spec"]["containers"][0]
    if not re.fullmatch(
        r"us-east1-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/sdp-evaluation-images/google-sdp-context@sha256:[0-9a-f]{64}",
        c["image"],
    ):
        raise ValueError
    if c["args"] != ["--live"] or job["spec"]["activeDeadlineSeconds"] != 900:
        raise ValueError
    acknowledgements = [
        v for v in c["env"] if v["name"] == "PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK"
    ]
    if acknowledgements != [
        {
            "name": "PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK",
            "value": "I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY",
        }
    ]:
        raise ValueError
    if any(v["name"] == "PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK" for v in c["env"]):
        raise ValueError
    expected = yaml.safe_load(
        (ROOT / "kubernetes/apps/google-sdp-evaluation/job.yaml").read_text()
    )
    expected["metadata"]["name"] = "google-sdp-context-evaluation"
    expected_container = expected["spec"]["template"]["spec"]["containers"][0]
    expected_container["image"] = c["image"]
    expected_container["env"] = [
        {"name": "PORTFOLIO_GOOGLE_SDP_PROJECT_ID", "value": c["image"].split("/")[1]},
        {
            "name": "PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK",
            "value": "I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY",
        },
    ]
    # Exact template equivalence rejects command/init-container/volume/hostAlias
    # additions that could bypass the fixed corpus or SDK attempt budget.
    if job != expected:
        raise ValueError
    # Check the complete original security contract, without changing templates.
    job["metadata"]["name"] = "google-sdp-evaluation"
    maps[0]["data"]["synthetic_corpus_path"] = "/app/evaluation/google-sdp/corpus.json"
    acknowledgements[0]["name"] = "PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK"
    acknowledgements[0]["value"] = "I_ACKNOWLEDGE_SYNTHETIC_ONLY_GOOGLE_SDP_EVALUATION"
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "security-validation.yaml"
        target.write_text(yaml.safe_dump_all(documents, sort_keys=False))
        (target.parent / "google-sdp-evaluation-controls.yaml").write_text(
            yaml.safe_dump_all(
                [v for v in documents if v["kind"] != "Job"], sort_keys=False
            )
        )
        (target.parent / "google-sdp-evaluation-job.yaml").write_text(
            yaml.safe_dump(job, sort_keys=False)
        )
        for name in ("google-sdp-egress-preflight.yaml", "networklogging.yaml"):
            shutil.copyfile(Path(path).parent / name, target.parent / name)
        subprocess.run(
            [
                "bash",
                str(ROOT / "scripts/validate-google-sdp-deployment.sh"),
                str(target),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError
        validate(sys.argv[1])
    except Exception:
        raise SystemExit("context deployment contract rejected") from None
    print("PASS: context profile and inherited deployment security contract")
