from __future__ import annotations

from typing import Any

from ..domain.status import BLOCKED, FAIL, NOT_RUN, PASS, SKIP
from ..normalize.canonicalize import canonical_result_map


def compare_coverage(plan: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    result_map = canonical_result_map(results)
    rows = []
    counts = {PASS: 0, FAIL: 0, BLOCKED: 0, SKIP: 0, NOT_RUN: 0}
    for test in plan.get("tests", []):
        result = result_map.get(test["test_id"])
        status = result.get("status", NOT_RUN) if result else NOT_RUN
        if status not in counts:
            counts[status] = 0
        counts[status] += 1
        rows.append(
            {
                "test_id": test["test_id"],
                "title": test.get("title", ""),
                "feature_area": test.get("feature_area", ""),
                "priority": test.get("priority", ""),
                "owner": test.get("owner", ""),
                "status": status,
                "summary": result.get("summary", "No result record exists.") if result else "No result record exists.",
            }
        )
    return {
        "total": len(plan.get("tests", [])),
        "counts": counts,
        "rows": rows,
    }
