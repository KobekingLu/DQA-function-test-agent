from __future__ import annotations

from typing import Any


def analyze_test_report(report: dict[str, Any]) -> dict[str, Any]:
    expected_tests = report["parsed"].get("expected_tests", {}).get("tests", [])
    actual_results = report["parsed"].get("actual_results", {}).get("by_test_id", {})
    known_issues = report["parsed"].get("known_issues", [])

    mismatch_items: list[dict[str, Any]] = []
    executed_count = 0
    pass_count = 0
    fail_count = 0
    blocked_count = 0
    coverage_gap_count = 0

    for test in expected_tests:
        test_id = test.get("test_id", "")
        actual = actual_results.get(test_id)
        priority = test.get("priority", "P2")
        severity = _priority_to_severity(priority)
        test_label = f"{test_id} - {test.get('test_name', '')}".strip(" -")

        if not actual:
            coverage_gap_count += 1
            mismatch_items.append(
                {
                    "test_id": test_id,
                    "test_name": test.get("test_name", ""),
                    "feature_area": test.get("feature_area", ""),
                    "priority": priority,
                    "category": "evidence_gap",
                    "status": "MISSING",
                    "severity": severity,
                    "summary": f"Agent found no actual execution record for {test_label}.",
                    "expected": test.get("expected_result", ""),
                    "actual": "Missing execution record",
                    "owner": test.get("owner", "DQA"),
                }
            )
            continue

        status = (actual.get("status") or "").upper()
        if status == "PASS":
            executed_count += 1
            pass_count += 1
            continue

        if status in {"FAIL", "BLOCKED"}:
            executed_count += 1
            if status == "FAIL":
                fail_count += 1
            else:
                blocked_count += 1

            mismatch_items.append(
                {
                    "test_id": test_id,
                    "test_name": test.get("test_name", ""),
                    "feature_area": test.get("feature_area", ""),
                    "priority": priority,
                    "category": "function_failure",
                    "status": status,
                    "severity": severity,
                    "summary": f"Agent detected {status.lower()} status on {test_label}.",
                    "expected": test.get("expected_result", ""),
                    "actual": actual.get("evidence") or actual.get("note") or status,
                    "owner": test.get("owner", "DQA"),
                    "log_reference": actual.get("log_reference", ""),
                }
            )
            continue

        coverage_gap_count += 1
        mismatch_items.append(
            {
                "test_id": test_id,
                "test_name": test.get("test_name", ""),
                "feature_area": test.get("feature_area", ""),
                "priority": priority,
                "category": "evidence_gap",
                "status": status or "NOT_RUN",
                "severity": severity,
                "summary": f"Agent found incomplete execution coverage for {test_label}.",
                "expected": test.get("expected_result", ""),
                "actual": actual.get("note") or status or "Not run",
                "owner": test.get("owner", "DQA"),
                "log_reference": actual.get("log_reference", ""),
            }
        )

    matched_issues = match_known_issues(mismatch_items, known_issues)
    decision = make_decision(mismatch_items, matched_issues)

    result = dict(report)
    result["analysis"] = {
        "total_test_count": len(expected_tests),
        "executed_count": executed_count,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "blocked_count": blocked_count,
        "coverage_gap_count": coverage_gap_count,
        "mismatch_items": mismatch_items,
        "matched_known_issues": matched_issues,
        **decision,
    }
    return result


def match_known_issues(
    mismatch_items: list[dict[str, Any]],
    known_issues: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not known_issues:
        return []

    mismatch_test_ids = {
        item.get("test_id", "")
        for item in mismatch_items
        if item.get("test_id")
    }

    matched: list[dict[str, str]] = []
    for issue in known_issues:
        if issue.get("status", "").lower() not in {"open", "waived"}:
            continue
        if issue.get("related_test_id", "") in mismatch_test_ids:
            matched.append(issue)
    return matched


def make_decision(
    mismatch_items: list[dict[str, Any]],
    matched_issues: list[dict[str, str]],
) -> dict[str, Any]:
    blocking_failures = [
        item
        for item in mismatch_items
        if item.get("category") == "function_failure" and item.get("severity") == "high"
    ]
    non_blocking_failures = [
        item
        for item in mismatch_items
        if item.get("category") == "function_failure" and item.get("severity") != "high"
    ]
    evidence_gaps = [item for item in mismatch_items if item.get("category") == "evidence_gap"]
    blocking_issues = [
        issue
        for issue in matched_issues
        if issue.get("severity", "").lower() in {"critical", "high"}
        and issue.get("disposition", "").lower() not in {"waived", "accepted"}
    ]

    if blocking_failures or blocking_issues:
        summary_text = "Agent found blocking function-test failures or open blocking issues, so release should stop."
        risk_level = "High"
        recommendation = "Block Release"
        recommended_owner = _pick_owner(blocking_issues, blocking_failures, "DQA + RD")
        suggested_next_step = "Stop exit review, assign failure owner, and collect fix plus retest evidence."
        decision_reasons = _decision_reasons(blocking_failures, evidence_gaps, blocking_issues)
        action_items = _action_items(blocking_failures, evidence_gaps, blocking_issues, recommendation)
    elif evidence_gaps or non_blocking_failures or matched_issues:
        summary_text = "Agent found missing evidence or non-blocking failures and recommended controlled retest."
        risk_level = "Medium"
        recommendation = "Retest Required"
        recommended_owner = _pick_owner(matched_issues, non_blocking_failures, "DQA")
        suggested_next_step = "Close missing coverage, confirm issue disposition, and rerun affected tests."
        decision_reasons = _decision_reasons(non_blocking_failures, evidence_gaps, matched_issues)
        action_items = _action_items(non_blocking_failures, evidence_gaps, matched_issues, recommendation)
    else:
        summary_text = "Agent found full execution coverage with no blocking failures and recommended the test cycle can exit."
        risk_level = "Low"
        recommendation = "Ready for Exit"
        recommended_owner = "DQA"
        suggested_next_step = "Package evidence and hand off the function-test review result."
        decision_reasons = [
            "All expected tests have executable evidence.",
            "Agent did not detect blocking failures.",
            "No open blocking issue is mapped to the reviewed test set.",
        ]
        action_items = [
            "Publish the reviewed test summary to the exit checkpoint.",
            "Keep traceability between test result and evidence link.",
        ]

    evidence_summary = [
        f"Function-test mismatches: {len(mismatch_items)}",
        f"Matched open or waived issues: {len(matched_issues)}",
    ]
    problem_details = [item["summary"] for item in mismatch_items] or ["Agent did not detect blocking function-test problems."]

    return {
        "risk_level": risk_level,
        "recommendation": recommendation,
        "summary_text": summary_text,
        "recommended_owner": recommended_owner,
        "suggested_next_step": suggested_next_step,
        "decision_reasons": decision_reasons,
        "action_items": action_items,
        "evidence_summary": evidence_summary,
        "problem_details": problem_details,
    }


def _priority_to_severity(priority: str) -> str:
    priority = (priority or "").upper()
    if priority in {"P0", "P1"}:
        return "high"
    if priority == "P2":
        return "medium"
    return "low"


def _pick_owner(
    issues: list[dict[str, Any]],
    mismatch_items: list[dict[str, Any]],
    fallback: str,
) -> str:
    for issue in issues:
        owner = issue.get("owner", "").strip()
        if owner:
            return owner
    for item in mismatch_items:
        owner = item.get("owner", "").strip()
        if owner:
            return owner
    return fallback


def _decision_reasons(
    mismatch_items: list[dict[str, Any]],
    evidence_gaps: list[dict[str, Any]],
    matched_issues: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if mismatch_items:
        reasons.append(f"Agent detected {len(mismatch_items)} test items with failure or blocked status.")
    if evidence_gaps:
        reasons.append(f"Agent found {len(evidence_gaps)} coverage gaps or not-run records.")
    if matched_issues:
        reasons.append(f"Agent matched {len(matched_issues)} open or waived issues against affected tests.")
    return reasons or ["Agent did not detect decision-changing issues."]


def _action_items(
    mismatch_items: list[dict[str, Any]],
    evidence_gaps: list[dict[str, Any]],
    matched_issues: list[dict[str, Any]],
    recommendation: str,
) -> list[str]:
    actions: list[str] = []
    if mismatch_items:
        actions.append("Review failing or blocked tests with owner and confirm fix target.")
    if evidence_gaps:
        actions.append("Fill the missing execution evidence before the next checkpoint.")
    if matched_issues:
        actions.append("Confirm each mapped issue disposition and attach the latest status.")
    if recommendation == "Block Release":
        actions.append("Keep the release gate closed until fix and retest evidence are available.")
    return actions or ["No immediate action item is required beyond publishing the review result."]
