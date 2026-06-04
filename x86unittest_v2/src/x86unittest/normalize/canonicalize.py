from __future__ import annotations

from typing import Any


def canonical_result_map(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item.get("test_id", ""): item for item in results.get("results", []) if item.get("test_id")}
