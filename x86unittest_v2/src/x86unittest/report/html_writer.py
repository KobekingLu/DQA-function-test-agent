from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .bilingual import label


def write_html_report(
    path: Path,
    plan: dict[str, Any],
    results: dict[str, Any],
    evidence: dict[str, Any],
    analysis: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_html(plan, results, evidence, analysis), encoding="utf-8")


def build_html(
    plan: dict[str, Any],
    results: dict[str, Any],
    evidence: dict[str, Any],
    analysis: dict[str, Any],
) -> str:
    decision = analysis["decision"]
    rows = "".join(build_coverage_row(row) for row in analysis["coverage"]["rows"])
    actions = "".join(f"<li>{html.escape(item)}</li>" for item in decision.get("action_items", []))
    missing_tools = analysis.get("preflight", {}).get("missing_tools", [])
    tools = "".join(
        f"<li>{html.escape(item.get('tool', ''))}: {html.escape(item.get('reason', ''))}</li>"
        for item in missing_tools
    ) or "<li>No missing tools recorded.</li>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>X86UniTest v2 Review</title>
  <style>
    body {{
      margin: 0;
      font-family: "Segoe UI", "Noto Sans TC", sans-serif;
      color: #17202a;
      background: #f6f8fa;
      line-height: 1.55;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px;
    }}
    section {{
      margin: 0 0 18px;
      padding: 18px;
      background: #ffffff;
      border: 1px solid #d7dde5;
      border-radius: 8px;
    }}
    h1, h2 {{
      margin: 0 0 10px;
      line-height: 1.25;
    }}
    .pill {{
      display: inline-block;
      padding: 4px 8px;
      border-radius: 6px;
      color: #ffffff;
      font-weight: 700;
      background: #607d8b;
    }}
    .High, .Block {{
      background: #b42318;
    }}
    .Medium, .Retest {{
      background: #ad6b00;
    }}
    .Low, .Ready {{
      background: #287d3c;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      border-bottom: 1px solid #d7dde5;
      padding: 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      font-size: 14px;
    }}
    .meta {{
      color: #536471;
    }}
  </style>
</head>
<body>
<main>
  <section>
    <h1>X86UniTest v2 Review</h1>
    <p class="meta">{html.escape(plan.get("product_name", ""))} / {html.escape(plan.get("profile_id", ""))}</p>
    <p><span class="pill {html.escape(decision["risk_level"])}">{html.escape(decision["risk_level"])}</span>
    <span class="pill {html.escape(decision["recommendation"].split()[0])}">{html.escape(decision["recommendation"])}</span></p>
    <p>{html.escape(decision.get("summary_text", ""))}</p>
  </section>
  <section>
    <h2>{html.escape(label("preflight"))}</h2>
    <ul>{tools}</ul>
  </section>
  <section>
    <h2>{html.escape(label("coverage"))}</h2>
    <table>
      <thead>
        <tr>
          <th>Test ID</th>
          <th>Feature</th>
          <th>Title</th>
          <th>Priority</th>
          <th>Status</th>
          <th>Summary</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
  <section>
    <h2>{html.escape(label("actions"))}</h2>
    <ul>{actions}</ul>
  </section>
  <section>
    <h2>Evidence / 證據</h2>
    <p>Collector: {html.escape(evidence.get("collector", ""))}</p>
    <p>Collected at: {html.escape(evidence.get("collected_at", ""))}</p>
    <p>Result records: {len(results.get("results", []))}</p>
  </section>
</main>
</body>
</html>
"""


def build_coverage_row(row: dict[str, Any]) -> str:
    return """
      <tr>
        <td>{test_id}</td>
        <td>{feature}</td>
        <td>{title}</td>
        <td>{priority}</td>
        <td>{status}</td>
        <td>{summary}</td>
      </tr>
    """.format(
        test_id=html.escape(row.get("test_id", "")),
        feature=html.escape(row.get("feature_area", "")),
        title=html.escape(row.get("title", "")),
        priority=html.escape(row.get("priority", "")),
        status=html.escape(row.get("status", "")),
        summary=html.escape(row.get("summary", "")),
    )
