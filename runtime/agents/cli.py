"""Offline synthetic entry points; no live integration switch."""

import argparse
import json
from runtime.agents.demo import make_demo


def main(profile):
    parser = argparse.ArgumentParser(
        description="Offline synthetic agent; simulated authentication, not a real model result."
    )
    parser.add_argument(
        "--user",
        choices=("demo-alpha", "demo-beta"),
        default="demo-alpha",
        help="Trusted startup simulated identity",
    )
    parser.add_argument("--language", choices=("en", "ar"), default="en")
    if profile == "infrastructure":
        parser.add_argument(
            "--scenario",
            choices=("archive-export", "docker-config", "cluster-version"),
            default="archive-export",
        )
    else:
        parser.add_argument(
            "--period", help="Reporting month YYYY-MM; omitted means clarification"
        )
    args = parser.parse_args()
    message = (
        {
            "en": "Diagnose this synthetic infrastructure failure.",
            "ar": "شخّص فشل البنية التحتية الاصطناعي.",
        }
        if profile == "infrastructure"
        else {"en": "Analyze synthetic expenses.", "ar": "حلل المصاريف الاصطناعية."}
    )[args.language]
    core, authorization = make_demo(profile, args.user)
    result = core.run(
        authorization,
        {
            "agent": profile,
            "message": message,
            "period": getattr(args, "period", None),
            "scenario_id": getattr(args, "scenario", None),
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "blocked" else 0
