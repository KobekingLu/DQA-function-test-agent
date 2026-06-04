from __future__ import annotations

from typing import Any


def match_issues(findings: list[dict[str, Any]], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    affected = {item.get("test_id") for item in findings}
    return [issue for issue in issues if issue.get("related_test_id") in affected]
