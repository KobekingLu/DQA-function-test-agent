from __future__ import annotations

import json
from pathlib import Path

from function_test_agent.decision import analyze_test_report
from function_test_agent.demo_case_parser import inspect_demo_cases
from function_test_agent.html_report import generate_html_reports
from function_test_agent.live_case_builder import build_latest_live_case


def main() -> None:
    project_root = Path(__file__).resolve().parent
    demo_cases_dir = project_root / "demo_cases"
    output_dir = project_root / "output"
    project_name = "DQA Function Test Review Agent"
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_reports = inspect_demo_cases(demo_cases_dir)
    live_case = build_latest_live_case(project_root)
    if live_case:
        raw_reports.append(live_case)
    analyzed_reports = []
    for report in raw_reports:
        analyzed = analyze_test_report(report)
        overrides = report.get("analysis_overrides", {})
        if overrides:
            analyzed["analysis"].update(overrides)
        analyzed_reports.append(analyzed)

    inventory = [
        {
            "case_name": report["case_name"],
            "source_type": report.get("source_type", "demo_case"),
            "source_label": report.get("source_label", "Fake Function Test Data"),
            "role_candidates": report["role_candidates"],
            "summary": report.get("analysis", {}).get("summary_text", ""),
        }
        for report in analyzed_reports
    ]

    summary = {
        "project_name": project_name,
        "demo_cases_folder": str(demo_cases_dir),
        "inventory": inventory,
        "reports": analyzed_reports,
        "notes": [
            "Version 1 uses simplified fake cases to keep the DQA function-test demo runnable.",
            "The same agent pattern is reused: inspect inputs, compare evidence, review issues, and recommend next action.",
            "This folder is intended to grow toward real test-plan and execution-report inputs.",
            "When a reachable DUT has live evidence under output/remote_runs, the demo also adds a live review case.",
        ],
    }

    _write_json(output_dir / "case_inventory.json", inventory)
    _write_json(output_dir / "function_test_summary.json", summary)

    for report in analyzed_reports:
        filename = f"{report['case_id']}_analysis.json"
        _write_json(output_dir / filename, report)

    html_outputs = generate_html_reports(analyzed_reports, output_dir, project_name)
    _print_summary(analyzed_reports, output_dir, html_outputs["overview"])


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _print_summary(reports: list[dict], output_dir: Path, overview_html: Path) -> None:
    print("=" * 72)
    print("DQA Function Test Review Agent Demo")
    print("=" * 72)
    print()
    for report in reports:
        analysis = report.get("analysis", {})
        print("-" * 72)
        print(f"Case: {report['case_name']}")
        print(f"Source: {report.get('source_label', 'Fake Function Test Data')}")
        print(f"Risk: {analysis.get('risk_level', 'N/A')}")
        print(f"Recommendation: {analysis.get('recommendation', 'N/A')}")
        print(f"Summary: {analysis.get('summary_text', 'N/A')}")
        print(f"Executed tests: {analysis.get('executed_count', 0)}/{analysis.get('total_test_count', 0)}")
        print(f"Pass: {analysis.get('pass_count', 0)}")
        print(f"Fail: {analysis.get('fail_count', 0)}")
        print(f"Blocked: {analysis.get('blocked_count', 0)}")
        print(f"Missing or not run: {analysis.get('coverage_gap_count', 0)}")
        if analysis.get("decision_reasons"):
            print("Decision reasons:")
            for reason in analysis["decision_reasons"]:
                print(f"  - {reason}")
        print()

    print("-" * 72)
    print(f"JSON output: {output_dir}")
    print(f"HTML overview: {overview_html}")


if __name__ == "__main__":
    main()
