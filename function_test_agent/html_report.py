from __future__ import annotations

import html
from pathlib import Path
from typing import Any


SUMMARY_TRANSLATIONS = {
    "Agent found full execution coverage with no blocking failures and recommended the test cycle can exit.": "Agent 找到完整的執行覆蓋，且沒有阻擋性 failure，因此建議本輪 function test 可以完成 exit review。",
    "Agent found missing evidence or non-blocking failures and recommended controlled retest.": "Agent 發現證據缺口或非阻擋性 failure，因此建議先在受控條件下補件與 retest。",
    "Agent found blocking function-test failures or open blocking issues, so release should stop.": "Agent 發現阻擋性 function-test failure 或開啟中的阻擋議題，因此建議暫停 release。",
}


def generate_html_reports(
    reports: list[dict[str, Any]],
    output_dir: Path,
    project_name: str,
) -> dict[str, Path]:
    report_dir = output_dir / "html"
    report_dir.mkdir(parents=True, exist_ok=True)

    detail_paths: dict[str, Path] = {}
    for report in reports:
        target_path = report_dir / f"{report['case_id']}.html"
        target_path.write_text(_build_detail_html(report, project_name), encoding="utf-8")
        detail_paths[report["case_id"]] = target_path

    overview_path = report_dir / "index.html"
    overview_path.write_text(_build_overview_html(reports, project_name, detail_paths), encoding="utf-8")
    return {"overview": overview_path, **detail_paths}


def _build_overview_html(
    reports: list[dict[str, Any]],
    project_name: str,
    detail_paths: dict[str, Path],
) -> str:
    rows: list[str] = []
    for report in reports:
        analysis = report.get("analysis", {})
        rows.append(
            """
            <tr>
              <td><a href="{href}">{case_name}</a></td>
              <td>{expected}</td>
              <td>{actual}</td>
              <td>{issues}</td>
              <td><span class="pill {risk_class}">{risk}</span></td>
              <td><span class="pill {rec_class}">{recommendation}</span></td>
              <td>{coverage}</td>
              <td>{summary}</td>
            </tr>
            """.format(
                href=html.escape(detail_paths[report["case_id"]].name),
                case_name=html.escape(report["case_name"]),
                expected=html.escape(report["role_candidates"].get("expected_tests", "")),
                actual=html.escape(report["role_candidates"].get("actual_results", "")),
                issues=html.escape(report["role_candidates"].get("known_issues", "")),
                risk=html.escape(_bilingual_risk(analysis.get("risk_level", "N/A"))),
                recommendation=html.escape(_bilingual_recommendation(analysis.get("recommendation", "N/A"))),
                coverage=html.escape(
                    f"{analysis.get('executed_count', 0)}/{analysis.get('total_test_count', 0)} executed"
                ),
                summary=_bilingual_summary_html(analysis.get("summary_text", "")),
                risk_class=_risk_class(analysis.get("risk_level", "")),
                rec_class=_recommendation_class(analysis.get("recommendation", "")),
            )
        )

    body = """
    <section class="hero">
      <div class="eyebrow">AI Agent Workflow Demo / AI Agent 工作流程示意</div>
      <h1>{project_name}</h1>
      <p class="hero-summary">AI agent review flow for DQA function testing.</p>
      <p class="zh-note">這是一個協助 DQA 做 function 測試審查與 test exit review 的 AI Agent demo。</p>
      <p>The agent inspects expected tests, actual execution result, and known issues, then explains whether the cycle is ready to exit, needs retest, or must block release.</p>
      <p class="zh-note">Agent 會盤點 expected test、actual execution result 與 known issues，並說明這一輪測試是可以 exit、需要 retest，或必須 block release。</p>
    </section>
    <section class="panel">
      <h2>Agent Workflow / Agent 工作流程</h2>
      <ol class="steps">
        <li>Inspect expected test plan / 盤點預期測試項目</li>
        <li>Read actual execution result / 讀取實際執行結果</li>
        <li>Match known issues / 對照已知議題</li>
        <li>Detect fail, blocked, and missing evidence / 找出 fail、blocked 與證據缺口</li>
        <li>Recommend next action / 建議下一步</li>
      </ol>
    </section>
    <section class="panel">
      <h2>Demo Cases / Demo 案例</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Case / 案例</th>
              <th>Expected / 預期</th>
              <th>Actual / 實際</th>
              <th>Known Issues / 已知議題</th>
              <th>Risk / 風險</th>
              <th>Recommendation / 建議</th>
              <th>Coverage / 覆蓋率</th>
              <th>Summary / 摘要</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
    </section>
    """.format(project_name=html.escape(project_name), rows="".join(rows))
    return _wrap_html("DQA Function Test Review Agent", body)


def _build_detail_html(report: dict[str, Any], project_name: str) -> str:
    analysis = report.get("analysis", {})
    expected_tests = report.get("parsed", {}).get("expected_tests", {}).get("tests", [])
    actual_by_test_id = report.get("parsed", {}).get("actual_results", {}).get("by_test_id", {})
    known_issues = analysis.get("matched_known_issues", [])

    body = """
    <nav class="back-link"><a href="index.html">Back to agent overview / 返回 Agent 總覽</a></nav>
    <section class="hero">
      <div class="eyebrow">Agent Decision Detail / Agent 決策細節</div>
      <h1>{case_name}</h1>
      <p>{project_name}</p>
      <div class="metric-grid">
        <div class="metric">
          <span class="label">Risk / 風險</span>
          <span class="pill {risk_class}">{risk}</span>
        </div>
        <div class="metric">
          <span class="label">Recommendation / 建議</span>
          <span class="pill {rec_class}">{recommendation}</span>
        </div>
        <div class="metric">
          <span class="label">Coverage / 覆蓋率</span>
          <span class="metric-value">{coverage}</span>
        </div>
      </div>
      <p class="hero-summary">{summary_text}</p>
      <p class="zh-note">{summary_zh}</p>
    </section>
    <section class="panel">
      <h2>Agent Decision Snapshot / Agent 決策快照</h2>
      {snapshot}
    </section>
    <section class="panel">
      <h2>Expected vs Actual Test Coverage / 預期與實際測試覆蓋</h2>
      {coverage_table}
    </section>
    <section class="panel">
      <h2>Detected Gaps and Failures / 偵測到的缺口與失敗</h2>
      {mismatch_table}
    </section>
    <section class="panel">
      <h2>Matched Known Issues / 命中的已知議題</h2>
      {issues_table}
    </section>
    <section class="panel split-panel">
      <div>
        <h2>Recommended Owner / 建議處理單位</h2>
        <p class="key-callout">{recommended_owner}</p>
      </div>
      <div>
        <h2>Suggested Next Step / 建議下一步</h2>
        <p class="key-callout">{suggested_next_step}</p>
      </div>
    </section>
    <section class="panel">
      <h2>Decision Reasons / 決策原因</h2>
      {reasons}
    </section>
    <section class="panel">
      <h2>Action Items / 後續動作</h2>
      {actions}
    </section>
    """.format(
        case_name=html.escape(report["case_name"]),
        project_name=html.escape(project_name),
        risk=html.escape(_bilingual_risk(analysis.get("risk_level", "N/A"))),
        recommendation=html.escape(_bilingual_recommendation(analysis.get("recommendation", "N/A"))),
        coverage=html.escape(f"{analysis.get('executed_count', 0)}/{analysis.get('total_test_count', 0)} executed"),
        summary_text=html.escape(analysis.get("summary_text", "")),
        summary_zh=html.escape(_summary_translation(analysis.get("summary_text", ""))),
        risk_class=_risk_class(analysis.get("risk_level", "")),
        rec_class=_recommendation_class(analysis.get("recommendation", "")),
        snapshot=_snapshot_cards(analysis),
        coverage_table=_coverage_table(expected_tests, actual_by_test_id),
        mismatch_table=_mismatch_table(analysis.get("mismatch_items", [])),
        issues_table=_issues_table(known_issues),
        recommended_owner=html.escape(analysis.get("recommended_owner", "N/A")),
        suggested_next_step=html.escape(analysis.get("suggested_next_step", "N/A")),
        reasons=_bullet_list(analysis.get("decision_reasons", []), "Agent did not record decision reasons."),
        actions=_bullet_list(analysis.get("action_items", []), "Agent did not record action items."),
    )
    return _wrap_html(f"DQA Function Test Detail - {report['case_name']}", body)


def _snapshot_cards(analysis: dict[str, Any]) -> str:
    items = [
        ("Total Tests / 總測項", str(analysis.get("total_test_count", 0))),
        ("Pass / 通過", str(analysis.get("pass_count", 0))),
        ("Fail / 失敗", str(analysis.get("fail_count", 0))),
        ("Blocked / 阻塞", str(analysis.get("blocked_count", 0))),
        ("Coverage Gaps / 缺口", str(analysis.get("coverage_gap_count", 0))),
    ]
    cards: list[str] = []
    for label, value in items:
        cards.append(
            """
            <div class="mini-card">
              <span class="label">{label}</span>
              <span class="metric-value">{value}</span>
            </div>
            """.format(label=html.escape(label), value=html.escape(value))
        )
    return '<div class="mini-card-grid">' + "".join(cards) + "</div>"


def _coverage_table(expected_tests: list[dict[str, Any]], actual_by_test_id: dict[str, dict[str, Any]]) -> str:
    rows: list[str] = []
    for test in expected_tests:
        actual = actual_by_test_id.get(test.get("test_id", ""), {})
        status = (actual.get("status") or "MISSING").upper()
        rows.append(
            """
            <tr>
              <td>{test_id}</td>
              <td>{feature_area}</td>
              <td>{test_name}</td>
              <td>{priority}</td>
              <td>{status}</td>
              <td>{evidence}</td>
            </tr>
            """.format(
                test_id=html.escape(test.get("test_id", "")),
                feature_area=html.escape(test.get("feature_area", "")),
                test_name=html.escape(test.get("test_name", "")),
                priority=html.escape(test.get("priority", "")),
                status=html.escape(status),
                evidence=html.escape(actual.get("evidence") or actual.get("note") or "N/A"),
            )
        )

    return """
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Test ID</th>
            <th>Feature</th>
            <th>Test Name</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """.format(rows="".join(rows))


def _mismatch_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p>Agent did not detect function-test gaps or failures.</p>"

    rows: list[str] = []
    for item in items:
        rows.append(
            """
            <tr>
              <td>{test_id}</td>
              <td>{category}</td>
              <td>{status}</td>
              <td>{severity}</td>
              <td>{summary}</td>
              <td>{owner}</td>
            </tr>
            """.format(
                test_id=html.escape(item.get("test_id", "")),
                category=html.escape(item.get("category", "")),
                status=html.escape(item.get("status", "")),
                severity=html.escape(item.get("severity", "")),
                summary=html.escape(item.get("summary", "")),
                owner=html.escape(item.get("owner", "")),
            )
        )

    return """
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Test ID</th>
            <th>Category</th>
            <th>Status</th>
            <th>Severity</th>
            <th>Summary</th>
            <th>Owner</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """.format(rows="".join(rows))


def _issues_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p>Agent did not match open or waived issues to the affected tests.</p>"

    rows: list[str] = []
    for item in items:
        rows.append(
            """
            <tr>
              <td>{issue_id}</td>
              <td>{related_test_id}</td>
              <td>{severity}</td>
              <td>{status}</td>
              <td>{disposition}</td>
              <td>{owner}</td>
              <td>{summary}</td>
            </tr>
            """.format(
                issue_id=html.escape(item.get("issue_id", "")),
                related_test_id=html.escape(item.get("related_test_id", "")),
                severity=html.escape(item.get("severity", "")),
                status=html.escape(item.get("status", "")),
                disposition=html.escape(item.get("disposition", "")),
                owner=html.escape(item.get("owner", "")),
                summary=html.escape(item.get("summary", "")),
            )
        )

    return """
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Issue ID</th>
            <th>Related Test</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Disposition</th>
            <th>Owner</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """.format(rows="".join(rows))


def _bullet_list(items: list[str], empty_text: str) -> str:
    if not items:
        return f"<p>{html.escape(empty_text)}</p>"
    body = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul class=\"bullet-list\">{body}</ul>"


def _bilingual_risk(value: str) -> str:
    mapping = {
        "Low": "Low / 低",
        "Medium": "Medium / 中",
        "High": "High / 高",
    }
    return mapping.get(value, value)


def _bilingual_recommendation(value: str) -> str:
    mapping = {
        "Ready for Exit": "Ready for Exit / 可完成 Exit Review",
        "Retest Required": "Retest Required / 需要補測",
        "Block Release": "Block Release / 阻擋 Release",
    }
    return mapping.get(value, value)


def _summary_translation(text: str) -> str:
    return SUMMARY_TRANSLATIONS.get(text, text)


def _bilingual_summary_html(text: str) -> str:
    translated = _summary_translation(text)
    return (
        '<div class="summary-stack">'
        f"<div>{html.escape(text)}</div>"
        f'<div class="zh-note">{html.escape(translated)}</div>'
        "</div>"
    )


def _risk_class(value: str) -> str:
    return {
        "Low": "risk-low",
        "Medium": "risk-medium",
        "High": "risk-high",
    }.get(value, "")


def _recommendation_class(value: str) -> str:
    return {
        "Ready for Exit": "risk-low",
        "Retest Required": "risk-medium",
        "Block Release": "risk-high",
    }.get(value, "")


def _wrap_html(title: str, body: str) -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1e8;
      --surface: #fffdf8;
      --text: #1f2933;
      --muted: #5b6875;
      --border: #d8cdb5;
      --green: #2f7d4a;
      --amber: #bf7b18;
      --red: #b33a2f;
      --teal: #1f6f78;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", Arial, sans-serif;
      line-height: 1.6;
    }}
    a {{ color: var(--teal); }}
    .hero, .panel {{
      max-width: 1120px;
      margin: 0 auto 18px;
      padding: 24px;
    }}
    .hero {{
      padding-top: 36px;
      padding-bottom: 12px;
    }}
    .eyebrow {{
      color: var(--muted);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    h1, h2 {{
      margin: 0 0 10px;
      line-height: 1.2;
    }}
    .hero-summary {{
      font-size: 18px;
      margin-top: 10px;
    }}
    .zh-note {{
      color: var(--muted);
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 10px;
      vertical-align: top;
      text-align: left;
    }}
    th {{
      font-size: 14px;
    }}
    .pill {{
      display: inline-block;
      padding: 4px 8px;
      border-radius: 8px;
      font-weight: 600;
      color: #fff;
    }}
    .risk-low {{ background: var(--green); }}
    .risk-medium {{ background: var(--amber); }}
    .risk-high {{ background: var(--red); }}
    .metric-grid, .mini-card-grid {{
      display: grid;
      gap: 12px;
    }}
    .metric-grid {{
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      margin-top: 14px;
    }}
    .mini-card-grid {{
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    }}
    .metric, .mini-card {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      background: #fffaf0;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 13px;
    }}
    .metric-value {{
      display: block;
      font-size: 22px;
      font-weight: 700;
      margin-top: 6px;
    }}
    .split-panel {{
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }}
    .key-callout {{
      font-size: 18px;
      font-weight: 600;
      margin: 0;
    }}
    .bullet-list, .steps {{
      margin: 0;
      padding-left: 20px;
    }}
    .back-link {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 20px 24px 0;
    }}
    .summary-stack > div + div {{
      margin-top: 4px;
    }}
    @media (max-width: 720px) {{
      .hero, .panel {{
        padding: 18px;
      }}
      .hero-summary {{
        font-size: 16px;
      }}
    }}
  </style>
</head>
<body>
{body}
</body>
</html>
""".format(title=html.escape(title), body=body)
