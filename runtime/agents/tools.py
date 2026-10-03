"""Five bounded read-only handlers; no shell, URLs, database or cloud clients."""

import json
from runtime.agents.schemas import ROOT, read_fixed
from runtime.phase3.trusted_runtime import ControlFailure


class DemoTools:
    def execute(self, invocation):
        tid, args, tenant = invocation.tool.id, invocation.arguments, invocation.tenant
        # Paths are code-selected; arguments only identify enum sections/months.
        if tid == "read_ci_summary":
            data = json.loads(read_fixed(ROOT / "demo/fixtures/ci.json"))
            if data.get("synthetic") is not True:
                raise ControlFailure("authorization", "denied")
            return {
                "source_id": data["source_id"],
                "synthetic": True,
                **data["scenarios"][args["scenario_id"]],
            }
        if tid == "read_image_summary":
            return json.loads(read_fixed(ROOT / "demo/fixtures/image.json"))
        if tid == "read_runbook_section":
            data = json.loads(read_fixed(ROOT / "demo/fixtures/runbooks.json"))
            if data.get("synthetic") is not True:
                raise ControlFailure("authorization", "denied")
            return {
                "source_id": data["source_id"] + ":" + args["section_id"],
                "synthetic": True,
                **data["sections"][args["section_id"]],
            }
        if tid in {"expense_summary", "expense_categories"}:
            data = json.loads(read_fixed(ROOT / "demo/fixtures/expenses.json"))
            if tenant.tenant_id not in data["tenants"] or data["synthetic"] is not True:
                raise ControlFailure("authorization", "denied")
            rows = [
                r
                for r in data["tenants"][tenant.tenant_id]
                if r["period"] == args["period"]
            ]
            if (
                any(
                    type(r["amount_minor_units"]) is not int
                    or not 0 < r["amount_minor_units"] < 100_000_000
                    for r in rows
                )
                or len(rows) > 20
            ):
                raise ControlFailure(
                    "structured_output_validation", "output_schema_mismatch"
                )
            common = {
                "source_id": data["source_id"],
                "synthetic": True,
                "period": args["period"],
                "currency": data["currency"],
                "data_available": bool(rows),
            }
            if tid == "expense_summary":
                return common | {
                    "total_minor_units": sum(r["amount_minor_units"] for r in rows),
                    "expense_count": len(rows),
                }
            groups = []
            for category in sorted({r["category"] for r in rows}):
                selected = [r for r in rows if r["category"] == category]
                groups.append(
                    {
                        "category": category,
                        "total_minor_units": sum(
                            r["amount_minor_units"] for r in selected
                        ),
                        "expense_count": len(selected),
                    }
                )
            groups.sort(key=lambda g: (-g["total_minor_units"], g["category"]))
            return common | {"categories": groups}
        raise ControlFailure("authorization", "denied")
