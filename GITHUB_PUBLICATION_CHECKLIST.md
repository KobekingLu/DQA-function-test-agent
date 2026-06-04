# GitHub Publication Checklist

Use this checklist before pushing this workspace to a public GitHub repository.

## Safe To Publish

- `README.md`
- `NEXT_STEP.md`
- `X86UNITEST_V2_ARCHITECTURE.md`
- `demo.py`
- `demo_cases/`
- `function_test_agent/`
- `x86unittest_v2/`
- `Script/dqa_live_checks/`
- `config/target_system.example.json`

## Keep Local Or Private

- `config/*.local.json`
- `output/`
- `Document/`
- `NeedtoDebug/`
- `NEW_Script/`
- full legacy tool bundles under `Script/`
- raw DUT logs, debug ZIP files, reports, images, videos, firmware, and customer documents

## Pre-Push Checks

Run these before pushing:

```bash
git status --short
git diff --cached --name-only
rg -n "password|passwd|secret|token|api[_-]?key|Techx86|172\\.17\\.|10\\.234\\." .
```

Expected notes:

- `config/target_system.example.json` may contain placeholder keys such as `password`, but not real credentials.
- Real SSH target files must stay in `config/*.local.json`.
- Generated v2 runs stay under `output/`, which is ignored.

## Recommended First Commit Scope

Stage only the cleaned public surface:

```bash
git add .gitignore .gitattributes README.md NEXT_STEP.md X86UNITEST_V2_ARCHITECTURE.md GITHUB_PUBLICATION_CHECKLIST.md demo.py demo_cases function_test_agent x86unittest_v2 Script/dqa_live_checks config/target_system.example.json
```
