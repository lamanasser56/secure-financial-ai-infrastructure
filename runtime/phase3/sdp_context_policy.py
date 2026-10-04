"""Versioned, unwired context/pattern candidate; no identifier validation.

Configuration is fixed by the committed artifact. Python reference matching is
evaluation only: it is not selected as a redactor or claimed to emulate Google.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from .google_sdp_adapter import GoogleSDPFailure, GoogleSDPRedactor, _guarded
from .trusted_runtime import SUPPORTED_ENTITIES

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "evaluation/google-sdp-context"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def load_policy():
    def read():
        raw = (DIRECTORY / "policy.json").read_bytes()
        if len(raw) > 32768:
            raise ValueError
        value = json.loads(raw, object_pairs_hook=_unique)
        if (
            set(value) != {"schema_version", "policy_id", "mapping", "inspect_config"}
            or value["schema_version"] != 1
            or value["policy_id"] != "context-pattern-v1"
            or set(value["mapping"].values()) != set(SUPPORTED_ENTITIES)
        ):
            raise ValueError
        config = value["inspect_config"]
        if (
            set(config)
            != {"info_types", "custom_info_types", "include_quote", "min_likelihood"}
            or config["include_quote"] is not False
            or config["min_likelihood"] != "POSSIBLE"
            or config["info_types"] != [{"name": "EMAIL_ADDRESS"}]
        ):
            raise ValueError
        names = {"EMAIL_ADDRESS"}
        for item in config["custom_info_types"]:
            if (
                set(item) != {"info_type", "regex", "likelihood"}
                or item["likelihood"] != "VERY_LIKELY"
                or not re.fullmatch(r"PORTFOLIO_[A-Z_]+", item["info_type"]["name"])
                or item["info_type"]["name"] in names
                or set(item["regex"]) != {"pattern", "group_indexes"}
                or item["regex"]["group_indexes"] != [1]
                or len(item["regex"]["pattern"]) > 2048
                or re.compile(item["regex"]["pattern"]).groups != 1
            ):
                raise ValueError
            names.add(item["info_type"]["name"])
        if names != set(value["mapping"]) or len(names) != 11:
            raise ValueError
        return value

    return _guarded(read)


def policy_digest():
    load_policy()
    return hashlib.sha256((DIRECTORY / "policy.json").read_bytes()).hexdigest()


def reference_spans(text):
    """Local exact-span assertions only; not a Google or runtime detector."""
    policy = load_policy()
    patterns = [("EMAIL_ADDRESS", r"([a-zA-Z0-9._%+-]+@example\.(?:invalid|com|org))")]
    patterns += [
        (v["info_type"]["name"], v["regex"]["pattern"])
        for v in policy["inspect_config"]["custom_info_types"]
    ]
    return sorted(
        (m.start(1), m.end(1), name)
        for name, pattern in patterns
        for m in re.finditer(pattern, text)
    )


class GoogleSDPContextRedactor(GoogleSDPRedactor):
    """Trusted startup only; existing SDK/deadline/budget/response guards reused."""

    def __init__(self, project_id, *, client=None, budget=None):
        self._policy = load_policy()
        super().__init__(project_id, client=client, budget=budget)

    def _type_map(self):
        return self._policy["mapping"]

    def _inspect_configuration(self):
        return deepcopy(self._policy["inspect_config"])

    def _normalized_output(self, original, spans, validated_output):
        # Reconstruct from validated coordinates, never replace arbitrary text
        # containing a technical type name. All nonsensitive text stays exact.
        pieces, cursor = [], 0
        for span in spans:
            pieces.extend(
                (original[cursor : span.start], self._policy["mapping"][span.info_type])
            )
            cursor = span.end
        pieces.append(original[cursor:])
        return "".join(pieces)
