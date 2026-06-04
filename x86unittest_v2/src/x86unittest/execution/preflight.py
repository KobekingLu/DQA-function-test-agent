from __future__ import annotations

import shutil
from typing import Any

from ..domain.status import BLOCKED, PASS


def run_preflight(profile: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    assumed = set(profile.get("tool_assumptions", []))
    required_tools = sorted(
        {
            tool
            for pack in plan.get("packs", [])
            for tool in pack.get("requires", [])
        }
    )
    checks = []
    missing_tools = []
    for tool in required_tools:
        present = tool in assumed or shutil.which(tool) is not None
        check = {
            "name": f"tool:{tool}",
            "tool": tool,
            "status": PASS if present else BLOCKED,
            "message": "available" if present else "missing",
            "assumed": tool in assumed,
        }
        checks.append(check)
        if not present:
            missing_tools.append({"tool": tool, "reason": "not found in PATH"})

    overall = BLOCKED if missing_tools else PASS
    return {
        "schema_version": "x86unittest.preflight.v1",
        "overall_status": overall,
        "required_tools": required_tools,
        "missing_tools": missing_tools,
        "checks": checks,
    }
