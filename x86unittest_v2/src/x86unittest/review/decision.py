from __future__ import annotations

from typing import Any

from ..domain.status import BLOCKED, FAIL, NOT_RUN, PASS, SKIP
from .coverage import compare_coverage
from .owner import pick_owner


def analyze_run(plan: dict[str, Any], results: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
    coverage = compare_coverage(plan, results)
    rows = coverage["rows"]
    blocking = [
        row for row in rows
        if row["status"] == FAIL and row.get("priority") in {"P0", "P1"}
    ]
    retest = [
        row for row in rows
        if row["status"] in {BLOCKED, SKIP, NOT_RUN}
    ]
    missing_tools = preflight.get("missing_tools", [])

    if blocking:
        recommendation = "Block Release"
        risk_level = "High"
        summary = "Blocking priority test failures require release stop."
        reasons = [f"{len(blocking)} high-priority test item(s) failed."]
    elif retest or missing_tools:
        recommendation = "Retest Required"
        risk_level = "Medium"
        summary = "The run needs executable evidence before exit review."
        reasons = []
        if retest:
            reasons.append(f"{len(retest)} planned test item(s) need execution or retest evidence.")
        if missing_tools:
            reasons.append(f"{len(missing_tools)} required tool(s) are missing in preflight.")
    else:
        recommendation = "Ready for Exit"
        risk_level = "Low"
        summary = "All planned tests have passing execution evidence."
        reasons = ["All planned test items passed."]

    action_items = build_action_items(recommendation, retest, missing_tools)
    decision = {
        "risk_level": risk_level,
        "recommendation": recommendation,
        "summary_text": summary,
        "decision_reasons": reasons,
        "recommended_owner": pick_owner(blocking or retest or rows),
        "suggested_next_step": action_items[0] if action_items else "Publish the reviewed package.",
        "action_items": action_items,
    }
    return {
        "schema_version": "x86unittest.analysis.v1",
        "profile_id": plan.get("profile_id", ""),
        "product_name": plan.get("product_name", ""),
        "coverage": coverage,
        "preflight": {
            "overall_status": preflight.get("overall_status", ""),
            "missing_tools": missing_tools,
        },
        "decision": decision,
    }


def build_action_items(
    recommendation: str,
    retest: list[dict[str, Any]],
    missing_tools: list[dict[str, Any]],
) -> list[str]:
    actions: list[str] = []
    if missing_tools:
        tools = ", ".join(item["tool"] for item in missing_tools)
        actions.append(f"Install or expose required tools before active execution: {tools}.")
    if retest:
        actions.append("Run active local, remote, or legacy adapters to replace skeleton SKIP/BLOCKED results.")
    if recommendation == "Block Release":
        actions.append("Keep release gate closed until failure owner provides fix and retest evidence.")
    return actions or ["Package evidence and publish the exit review result."]
