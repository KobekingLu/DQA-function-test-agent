from __future__ import annotations

from pathlib import Path
from typing import Any

from .control.export import export_run_zip
from .control.manifest import build_manifest
from .control.planner import build_plan
from .control.run_context import create_run_context
from .execution.collectors import collect_baseline_evidence, create_initial_results
from .execution.preflight import run_preflight
from .profiles.loader import load_profile
from .report.html_writer import write_html_report
from .report.json_writer import read_json, write_json
from .review.decision import analyze_run


class X86UniTestApp:
    def doctor(self, profile_ref: str, selected_packs: list[str] | None = None) -> dict[str, Any]:
        profile = load_profile(profile_ref)
        plan = build_plan(profile, selected_packs or [])
        preflight = run_preflight(profile, plan)
        return {
            "profile_id": profile["profile_id"],
            "product_name": profile.get("product_name", ""),
            "selected_pack_count": len(plan["packs"]),
            "selected_test_count": len(plan["tests"]),
            "overall_status": preflight["overall_status"],
            "missing_tools": preflight["missing_tools"],
            "checks": preflight["checks"],
            "remote_ready": bool(profile.get("remote", {}).get("enabled")),
        }

    def plan(self, profile_ref: str, selected_packs: list[str] | None = None) -> dict[str, Any]:
        profile = load_profile(profile_ref)
        return build_plan(profile, selected_packs or [])

    def run(
        self,
        profile_ref: str,
        selected_packs: list[str],
        output_dir: Path,
        collect_only: bool,
        target_config: str = "",
    ) -> dict[str, Any]:
        profile = load_profile(profile_ref)
        if target_config:
            profile.setdefault("remote", {})["target_config"] = target_config
        plan = build_plan(profile, selected_packs)
        context = create_run_context(output_dir, profile["profile_id"])
        manifest = build_manifest(context, profile, collect_only=collect_only)
        preflight = run_preflight(profile, plan)
        evidence = collect_baseline_evidence(profile, context, target_config=target_config)
        results = create_initial_results(plan, collect_only=collect_only)

        write_json(context.run_dir / "manifest.json", manifest)
        write_json(context.run_dir / "profile_snapshot.json", profile)
        write_json(context.run_dir / "plan.json", plan)
        write_json(context.run_dir / "preflight.json", preflight)
        write_json(context.run_dir / "evidence.json", evidence)
        write_json(context.run_dir / "results.json", results)

        return {
            "run_id": context.run_id,
            "run_dir": str(context.run_dir),
            "manifest_path": str(context.run_dir / "manifest.json"),
            "collect_only": collect_only,
        }

    def review(self, run_dir: Path) -> dict[str, Any]:
        plan = read_json(run_dir / "plan.json")
        results = read_json(run_dir / "results.json")
        preflight = read_json(run_dir / "preflight.json")
        evidence = read_json(run_dir / "evidence.json")
        analysis = analyze_run(plan, results, preflight)
        decision = analysis["decision"]

        analysis_path = run_dir / "analysis.json"
        decision_path = run_dir / "decision.json"
        html_path = run_dir / "html" / "index.html"
        write_json(analysis_path, analysis)
        write_json(decision_path, decision)
        write_html_report(html_path, plan, results, evidence, analysis)

        return {
            "run_dir": str(run_dir),
            "analysis_path": str(analysis_path),
            "decision_path": str(decision_path),
            "html_path": str(html_path),
            "recommendation": decision["recommendation"],
        }

    def export(self, run_dir: Path, export_format: str) -> dict[str, Any]:
        if export_format != "zip":
            raise ValueError(f"Unsupported export format: {export_format}")
        export_path = export_run_zip(run_dir)
        return {"run_dir": str(run_dir), "export_path": str(export_path)}
