# X86UniTest v2 Skeleton

This is the first runnable skeleton for the redesigned X86UniTest platform.

The goal is to move from a monolithic shell-driven tool to a profile-driven test platform with explicit planning, evidence, review, and export artifacts.

## Current Capabilities

- Load a product profile.
- Build a test plan from enabled packs.
- Run a readiness check with `doctor`.
- Create a run directory with manifest, plan, evidence, preflight, and results JSON.
- Review a run into `analysis.json`, `decision.json`, and bilingual HTML.
- Export a run directory as a ZIP package.

## Try It

From this folder's `src` directory:

```bash
python -m x86unittest.cli doctor --profile fwa6083
python -m x86unittest.cli plan --profile fwa6083
python -m x86unittest.cli run --profile fwa6083 --collect-only --output ../../output/v2_runs
python -m x86unittest.cli review --run ../../output/v2_runs/<run_id>
python -m x86unittest.cli export --run ../../output/v2_runs/<run_id>
```

## SSH DUT Direction

The skeleton already keeps remote execution as a first-class concept through profile metadata and adapter modules. The first remote implementation should reuse the existing `Script/dqa_live_checks/dqa_remote_run.py` behavior, then normalize downloaded `evidence.json` and `quick_check.json` into the v2 run shape.
