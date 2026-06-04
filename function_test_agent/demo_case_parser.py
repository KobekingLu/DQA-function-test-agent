from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def inspect_demo_cases(root: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for expected_path in sorted(root.glob("*_expected_tests.csv")):
        prefix = expected_path.name[: -len("_expected_tests.csv")]
        actual_path = root / f"{prefix}_actual_results.csv"
        issues_path = root / f"{prefix}_known_issues.csv"

        if not actual_path.exists() or not issues_path.exists():
            continue

        reports.append(
            {
                "case_id": prefix,
                "case_name": _display_name(prefix),
                "source_type": "demo_case",
                "source_label": "Fake Function Test Data",
                "sheet_names": [
                    expected_path.name,
                    actual_path.name,
                    issues_path.name,
                ],
                "role_candidates": {
                    "expected_tests": expected_path.name,
                    "actual_results": actual_path.name,
                    "known_issues": issues_path.name,
                },
                "parsed": {
                    "expected_tests": parse_expected_tests(expected_path),
                    "actual_results": parse_actual_results(actual_path),
                    "known_issues": parse_known_issues(issues_path),
                },
            }
        )
    return reports


def parse_expected_tests(path: Path) -> dict[str, Any]:
    tests: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            test_id = (row.get("test_id") or "").strip()
            if not test_id:
                continue
            tests.append(
                {
                    "test_id": test_id,
                    "feature_area": (row.get("feature_area") or "").strip(),
                    "test_name": (row.get("test_name") or "").strip(),
                    "priority": (row.get("priority") or "").strip().upper() or "P2",
                    "expected_result": (row.get("expected_result") or "").strip(),
                    "owner": (row.get("owner") or "").strip(),
                }
            )
    return {"source_sheet": path.name, "tests": tests}


def parse_actual_results(path: Path) -> dict[str, Any]:
    results: list[dict[str, str]] = []
    by_test_id: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            test_id = (row.get("test_id") or "").strip()
            if not test_id:
                continue
            item = {
                "test_id": test_id,
                "status": (row.get("status") or "").strip().upper(),
                "evidence": (row.get("evidence") or "").strip(),
                "log_reference": (row.get("log_reference") or "").strip(),
                "note": (row.get("note") or "").strip(),
            }
            results.append(item)
            by_test_id[test_id] = item
    return {"source_sheet": path.name, "items": results, "by_test_id": by_test_id}


def parse_known_issues(path: Path) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            issue_id = (row.get("issue_id") or "").strip()
            if not issue_id:
                continue
            issues.append(
                {
                    "issue_id": issue_id,
                    "related_test_id": (row.get("related_test_id") or "").strip(),
                    "severity": (row.get("severity") or "").strip(),
                    "status": (row.get("status") or "").strip(),
                    "disposition": (row.get("disposition") or "").strip(),
                    "owner": (row.get("owner") or "").strip(),
                    "summary": (row.get("summary") or "").strip(),
                }
            )
    return issues


def _display_name(prefix: str) -> str:
    mapping = {
        "ready": "Ready Demo Case",
        "conditional": "Retest Demo Case",
        "block": "Block Demo Case",
    }
    return mapping.get(prefix, prefix.replace("_", " ").title())
