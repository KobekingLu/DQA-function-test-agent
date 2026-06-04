from __future__ import annotations

import platform
from datetime import datetime
from typing import Any

from ..domain.status import BLOCKED, SKIP


def collect_baseline_evidence(
    profile: dict[str, Any],
    context: Any,
    target_config: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": "x86unittest.evidence.v1",
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "collector": "x86unittest_v2.skeleton",
        "run_id": context.run_id,
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "profile": {
            "profile_id": profile["profile_id"],
            "product_name": profile.get("product_name", ""),
        },
        "remote": {
            "target_config": target_config or profile.get("remote", {}).get("target_config", ""),
            "enabled": bool(target_config or profile.get("remote", {}).get("enabled")),
            "status": "recorded_only",
            "message": "Remote execution adapter is reserved for the next implementation slice.",
        },
    }


def create_initial_results(plan: dict[str, Any], collect_only: bool) -> dict[str, Any]:
    results = []
    status = SKIP if collect_only else BLOCKED
    message = (
        "Collect-only mode: active execution was intentionally skipped."
        if collect_only
        else "Active execution adapter is not implemented in this skeleton."
    )
    for test in plan.get("tests", []):
        results.append(
            {
                "test_id": test["test_id"],
                "status": status,
                "summary": message,
                "evidence": [],
                "findings": [
                    {
                        "category": "execution_not_started",
                        "severity": "medium",
                        "summary": message,
                        "suggested_owner": test.get("owner", "DQA"),
                        "suggested_action": "Run this pack with an implemented local, remote, or legacy adapter.",
                    }
                ],
                "runner": "skeleton.collect_only" if collect_only else "skeleton.blocked",
            }
        )
    return {
        "schema_version": "x86unittest.results.v1",
        "collect_only": collect_only,
        "results": results,
    }
