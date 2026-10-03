"""Closed, committed schema bindings; model input cannot choose a schema path."""

from copy import deepcopy
import json
import os
from pathlib import Path
import stat

from jsonschema import Draft202012Validator, FormatChecker
from runtime.phase3.trusted_runtime import ControlFailure

ROOT = Path(__file__).resolve().parents[2]
TOOL_IDS = frozenset(
    {
        "read_ci_summary",
        "read_image_summary",
        "read_runbook_section",
        "expense_summary",
        "expense_categories",
    }
)


def schema_ref(tool_id, direction):
    if tool_id not in TOOL_IDS or direction not in {"input", "output"}:
        raise ControlFailure("structured_input_validation", "unknown_tool")
    return f"contracts/agents/{tool_id}.{direction}.schema.json"


def read_fixed(path, maximum=16_384):
    """Only callers' committed allowlisted paths; reject symlinks at every level."""
    path = Path(path)
    if not path.is_relative_to(ROOT) or any(
        p.is_symlink() for p in (path, *path.parents)
    ):
        raise ValueError("fixture:invalid_source")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size > maximum
        ):
            raise ValueError("fixture:invalid_source")
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("fixture:oversized")
    return value.decode("utf-8")


def validate(name, value, stage="structured_input_validation"):
    category = (
        "output_schema_mismatch"
        if stage == "structured_output_validation"
        else "argument_schema_mismatch"
    )
    try:
        # Names are code-selected and never taken from a request or tool result.
        if name not in {"request", "decision"} | {
            f"{tool}.{direction}"
            for tool in TOOL_IDS
            for direction in ("input", "output")
        }:
            raise ValueError
        schema = json.loads(
            read_fixed(ROOT / "contracts/agents" / f"{name}.schema.json")
        )
        if len(json.dumps(value, ensure_ascii=False).encode()) > 8_192:
            raise ValueError
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    except Exception:
        raise ControlFailure(stage, category) from None
    return deepcopy(value)


def bound_metadata(tool, stage="structured_input_validation"):
    if tool.id in TOOL_IDS and (
        tool.input_schema_ref != schema_ref(tool.id, "input")
        or tool.output_schema_ref != schema_ref(tool.id, "output")
    ):
        raise ControlFailure(
            stage,
            (
                "output_schema_mismatch"
                if stage == "structured_output_validation"
                else "malformed_metadata"
            ),
        )
