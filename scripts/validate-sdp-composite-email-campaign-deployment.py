#!/usr/bin/env python3
"""Offline exact AM-R4 composite campaign profile plus the inherited security contract.

No resource application, cloud access or SDK client construction. Scope/attempt
annotations document the fixed harness behavior; the unchanged qualified image and exact
separately reviewed program enforce it. This validator does not qualify an arbitrary image digest.
"""

import copy
import hashlib
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
        "name": "PORTFOLIO_COMPOSITE_EMAIL_CAMPAIGN_ACK",
        "value": "I_ACKNOWLEDGE_COMPOSITE_EMAIL_CAMPAIGN_NOT_GOOGLE_QUALIFICATION",
    },
]


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key, value in node.value:
        name = loader.construct_object(key)
        if name in result:
            raise ValueError
        result[name] = loader.construct_object(value)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read_yaml(path):
    """Bound and reject special files before parsing trusted render output."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
        raise ValueError
    documents = list(yaml.load_all(path.read_text(encoding="utf-8"), Loader=UniqueLoader))
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
        r"us-east1-docker\.pkg\.dev/([a-z][a-z0-9-]{4,28}[a-z0-9])/sdp-evaluation-images/google-sdp-context@sha256:667ceec4b8290df1341a91a7685ad140319fca6d23f92b9948dddf9fac64136b",
        container["image"],
    )
    if match is None:
        raise ValueError
    # Exact equivalence rejects command, environment, selector, volume and resource
    # additions, as well as unsuspension, retries and a full-campaign entry point.
    expected = yaml.safe_load(
        (ROOT / "kubernetes/apps/google-sdp-evaluation/job.yaml").read_text()
    )
    import importlib.util
    spec = importlib.util.spec_from_file_location("composite_campaign", ROOT / "scripts/evaluate-composite-email-campaign.py")
    program = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(program)
    code = program.rendered_source(ROOT)
    expected["metadata"]["name"] = "google-sdp-composite-email-campaign"
    expected["metadata"]["annotations"] = {
        "portfolio.example/evaluation-scope": "composite-deterministic-email-plus-provider",
        "portfolio.example/content-attempt-limit": "172",
        "portfolio.example/program-sha256": hashlib.sha256(code.encode()).hexdigest(),
    }
    expected["spec"]["activeDeadlineSeconds"] = 900
    expected_container = expected["spec"]["template"]["spec"]["containers"][0]
    expected_container["image"] = container["image"]
    expected_container["command"] = ["/usr/local/bin/python3.12"]
    expected_container["args"] = ["-c", code, "--live"]
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
    container.pop("command")
    container["args"] = ["--live"]
    container["env"] = [
        {"name": "PORTFOLIO_GOOGLE_SDP_PROJECT_ID", "value": match.group(1)},
        {
            "name": "PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK",
            "value": "I_ACKNOWLEDGE_SYNTHETIC_ONLY_GOOGLE_SDP_EVALUATION",
        },
    ]
    maps[0]["data"]["synthetic_corpus_path"] = "/app/evaluation/google-sdp/corpus.json"
    with tempfile.TemporaryDirectory(prefix="portfolio-composite-validation-") as temporary:
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
        raise SystemExit("composite campaign deployment contract rejected") from None
    print("PASS: AM-R4 composite campaign profile and inherited deployment security contract; not Google qualification")
