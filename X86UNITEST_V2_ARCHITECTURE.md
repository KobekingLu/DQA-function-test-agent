# X86UniTest v2 Architecture Brief

## Purpose / 目標

X86UniTest v2 is a redesign of the current x86UniTest foundation from a script-driven test bundle into a data-driven DQA test platform.

X86UniTest v2 的目標不是把舊版 shell 包得更漂亮，而是讓 DQA / RD / Lab 使用者更容易設定、執行、追蹤、複測與交付證據。

The practical goal:

- A user can select a product profile, preview the test plan, run tests, resume interrupted runs, review failures, and export evidence without needing to understand the internal shell flow.
- A reviewer can inspect canonical JSON and bilingual HTML to understand coverage, failure reason, missing evidence, issue mapping, owner, and release risk.
- A maintainer can add a new test item or product profile without touching unrelated execution logic.

## Current Pain Points / 現況痛點

The current x86UniTest implementation is powerful, but the foundation makes long-term evolution difficult.

- Control flow, environment setup, execution, reboot handling, packaging, and report generation are concentrated in large shell scripts.
- Test selection is stored in text config files, but the meaning of each item is spread across shell functions and naming conventions.
- Runtime state is scattered across `work/`, `log/`, `cfg/`, and `/etc/x86UniTest.boot`.
- Reports are generated from logs after the fact, so the structured source of truth is weak.
- Users often discover missing tools, cabling issues, or unsupported cases only after running part of the test.
- Product differences become shell branches instead of explicit data.
- AI review can help explain the result, but the platform first needs reliable canonical evidence.

## Design Principles / 設計原則

- Declarative first: test intent, profile settings, requirements, and policy should be data.
- Evidence first: canonical JSON is the source of truth; text logs and HTML are derived outputs.
- Explicit state: every run has a manifest, configuration snapshot, evidence, result, and decision artifacts.
- Compatibility during migration: old entry points can remain as wrappers while internals move to v2.
- Policy separated from execution: command execution should not directly own release decision logic.
- Demo-friendly but production-shaped: output should be understandable in a demo and durable enough for real DQA evidence.
- Small modules, clear contracts: avoid creating a large framework before the first real workflow runs.

## Target Users / 使用者

- DQA engineer: prepares profiles, runs function tests, reviews failures, packages evidence.
- Lab engineer: validates setup readiness, cabling, power/reboot loops, device presence, and blocked conditions.
- RD owner: receives failing item context, logs, reproduction details, and retest requirements.
- PM / release reviewer: reads risk summary, exit recommendation, open issues, and action owner.
- Tool maintainer: adds packs, parsers, policies, and compatibility bridges.

## System Shape / 系統切分

X86UniTest v2 should be split into three planes.

### Control Plane

Owns user interaction, run lifecycle, profile resolution, planning, resume, and export.

Responsibilities:

- Parse CLI commands.
- Load product profile and selected test packs.
- Generate a run plan before execution.
- Create a run directory and manifest.
- Track run status and resumable checkpoints.
- Coordinate local or remote execution.
- Package artifacts.

### Execution Plane

Owns collectors, active tests, command execution, timeout handling, retry behavior, and raw artifacts.

Responsibilities:

- Run commands and scripts through a controlled adapter.
- Capture stdout, stderr, return code, timing, and log path.
- Execute local, remote SSH, or legacy shell tests.
- Collect preflight readiness evidence.
- Mark items `PASS`, `FAIL`, `BLOCKED`, or `SKIP` at the technical execution level.

### Review Plane

Owns normalization, coverage comparison, issue matching, policy decision, and human-readable reporting.

Responsibilities:

- Normalize expected tests, actual results, known issues, and waivers.
- Compare expected coverage with actual evidence.
- Detect missing evidence and blocked items.
- Match failures to known issues.
- Apply release / exit policy.
- Render JSON and bilingual HTML reports.

## Proposed Repository Layout / 建議目錄

```text
x86unittest_v2/
  README.md
  pyproject.toml

  scripts/
    x86UniTest.sh

  src/
    x86unittest/
      __init__.py
      cli.py
      app.py

      control/
        planner.py
        run_context.py
        manifest.py
        resume.py
        export.py

      domain/
        models.py
        status.py
        ids.py

      profiles/
        loader.py
        schema.py
        defaults/
          default.yaml
          fwa6083.yaml

      packs/
        registry.py
        bios/
        bmc/
        io/
        reliability/
        security/
        storage/
        network/

      execution/
        command_runner.py
        local_adapter.py
        remote_adapter.py
        legacy_shell_adapter.py
        preflight.py
        collectors.py

      ingest/
        expected_plan.py
        actual_results.py
        known_issues.py
        legacy_logs.py

      normalize/
        canonicalize.py
        field_map.py

      review/
        coverage.py
        issue_matching.py
        decision.py
        risk.py
        owner.py

      report/
        json_writer.py
        html_writer.py
        bilingual.py
        templates/
          overview.html
          detail.html
          style.css

      compat/
        legacy_cli.py
        legacy_config.py
        legacy_report.py

  tests/
    unit/
    fixtures/
```

This layout can live beside the current implementation at first. After v2 proves useful, old modules can be migrated pack by pack.

## Core Domain Model / 核心資料模型

### Profile

Product or platform-specific configuration.

Fields:

- `profile_id`
- `product_name`
- `platform`
- `owners`
- `hardware_expectations`
- `network_topology`
- `storage_topology`
- `enabled_packs`
- `default_policy`
- `tool_assumptions`
- `legacy_mapping`

### TestPack

A group of related test cases, such as BIOS, BMC, IO, Storage, Network, USB, or Reliability.

Fields:

- `pack_id`
- `name`
- `description`
- `requires`
- `test_cases`
- `default_timeout`
- `risk_tags`

### TestCase

The canonical definition of a test item.

Fields:

- `test_id`
- `title`
- `feature_area`
- `priority`
- `owner`
- `intent`
- `preconditions`
- `steps`
- `evidence_requirements`
- `pass_criteria`
- `blocked_criteria`
- `legacy_ids`

### TestResult

The actual result from one run.

Fields:

- `test_id`
- `status`
- `started_at`
- `finished_at`
- `duration_seconds`
- `evidence`
- `measurements`
- `findings`
- `log_references`
- `runner`

### Finding

A structured problem detected by execution or review.

Fields:

- `finding_id`
- `test_id`
- `category`
- `severity`
- `summary`
- `evidence_reference`
- `suggested_owner`
- `suggested_action`
- `matched_issue_id`

### Decision

Release / exit decision based on policy.

Fields:

- `risk_level`
- `recommendation`
- `decision_reasons`
- `recommended_owner`
- `suggested_next_step`
- `action_items`

## CLI Experience / CLI 體驗

The CLI should make the workflow visible before running destructive or long-duration actions.

```bash
x86uni doctor --profile fwa6083
x86uni plan --profile fwa6083 --pack io --pack bmc
x86uni run --profile fwa6083 --pack io --output output/runs
x86uni resume --run output/runs/fwa6083_20260604_101530
x86uni review --run output/runs/fwa6083_20260604_101530
x86uni export --run output/runs/fwa6083_20260604_101530 --format zip
```

Compatibility wrapper examples:

```bash
./x86UniTest.sh -first
./x86UniTest.sh -all
./x86UniTest.sh -report
./x86UniTest.sh -z
```

Legacy commands should map into v2 commands during migration.

| Legacy command | v2 behavior |
| --- | --- |
| `-first` | `doctor` + profile initialization + baseline evidence collection |
| `-all` | `plan` + `run` using enabled profile packs |
| `-summary` | render result summary from canonical JSON |
| `-report` | `review` + HTML report generation |
| `-z` | `export` run artifact package |

## Profile Example / Profile 範例

```yaml
profile_id: fwa6083
product_name: FWA-6083
platform: x86

owners:
  default: DQA
  bmc: DQA
  storage: DQA
  power: Lab
  firmware: RD

enabled_packs:
  - io.inventory
  - storage.smoke
  - network.link_readiness
  - bmc.sensor_fru

network_topology:
  external_interfaces:
    - ba4p0
    - ba5p0
  loopback_pairs:
    - [be1p0, be1p1]

storage_topology:
  boot_device_required: true
  smart_required: true
  smoke_test_dir: /var/tmp

policy:
  block_on:
    - priority: P0
      status: FAIL
    - severity: critical
      issue_status: open
  retest_on:
    - status: BLOCKED
    - missing_evidence: true

legacy_mapping:
  item_cfg:
    cpu_info: io.cpu_inventory
    ram_info: io.memory_inventory
    lan_info: network.inventory
    storage_info: storage.inventory
    usb_info: io.usb_inventory
    sdr_info: bmc.sensor_snapshot
```

## Test Pack Example / Test Pack 範例

```yaml
pack_id: storage.smoke
name: Storage Smoke
feature_area: Storage

test_cases:
  - test_id: STORAGE-001
    title: Boot storage visibility and health
    priority: P1
    owner: DQA
    intent: Confirm boot storage is visible and does not report SMART failure.
    steps:
      - type: collect
        command: lsblk -J -o NAME,PATH,TYPE,SIZE,MODEL,SERIAL,TRAN,MOUNTPOINTS
      - type: collect
        command: smartctl --scan -j
      - type: assert
        rule: storage.boot_device_present
      - type: assert
        rule: storage.smart_not_failed
    evidence_requirements:
      - block_device_inventory
      - smart_health
    pass_criteria:
      - boot device visible
      - no health failure keyword detected
    blocked_criteria:
      - smartctl missing
      - no storage device detected
```

## Run Output Shape / 輸出結構

Every run should have one self-contained directory.

```text
output/runs/fwa6083_20260604_101530/
  manifest.json
  profile_snapshot.yaml
  plan.json
  evidence.json
  results.json
  analysis.json
  decision.json
  logs/
    commands/
    tests/
  html/
    index.html
    detail.html
  export/
    fwa6083_20260604_101530.zip
```

Important rule: `analysis.json` and `decision.json` are derived from `plan.json`, `evidence.json`, `results.json`, and known issue inputs. HTML is derived from JSON, not from raw logs.

## Status Semantics / 狀態語意

- `PASS`: test ran and met criteria.
- `FAIL`: test ran and violated criteria.
- `BLOCKED`: test could not produce valid result because precondition, setup, cabling, missing tool, or dependency prevented execution.
- `SKIP`: intentionally not executed by profile, scope, or user selection.
- `NOT_RUN`: expected item has no actual execution record.
- `WARN`: evidence exists but needs human review; should not be used as final pass/fail without policy.

## Migration Strategy / 遷移策略

### Phase 1: Establish v2 contract

- Create canonical domain models.
- Define run output folder shape.
- Add CLI skeleton for `doctor`, `plan`, `run`, `review`, and `export`.
- Keep current `function_test_agent` outputs working.

### Phase 2: Wrap current tools

- Add `legacy_shell_adapter`.
- Map `template_item.cfg` to v2 test selections.
- Map `template_data.cfg` to profile fields.
- Parse old `x86UniTest_Result.log` and `x86UniTest_Summary_Result.log` into canonical results.

### Phase 3: Promote collectors

- Move current live-check collector concepts into v2 execution modules.
- Make preflight first-class.
- Produce `evidence.json` before active tests.

### Phase 4: Convert packs gradually

- Start with read-only IO inventory, storage, network, USB, and BMC sensor/FRU checks.
- Keep reliability and reboot-heavy flows behind legacy adapter until state handling is stable.
- Convert one pack at a time and compare v2 results with old reports.

### Phase 5: Retire monolithic behavior

- Keep `x86UniTest.sh` as a stable launcher.
- Move orchestration out of shell.
- Use structured run state instead of `/etc/x86UniTest.boot` wherever possible.

## First Implementation Slice / 第一個可落地版本

The first useful v2 slice should be small but real.

Scope:

- `x86uni doctor`
- `x86uni plan`
- `x86uni run --collect-only`
- `x86uni review`
- canonical JSON output
- bilingual HTML report
- one profile, likely `fwa6083`
- one or two packs, likely `io.inventory` and `storage.smoke`

This gives users a real improvement quickly: they can check readiness, collect evidence, review coverage, and generate a report without waiting for the full legacy migration.

## Open Decisions / 待決問題

- Should v2 live inside this repo first, or become a standalone repository after the first slice works?
- Should profile files use YAML, JSON, or both?
- What is the minimum supported Python version on target DUT images?
- Which reboot / power-cycle flows must remain shell-controlled during early migration?
- How should signed-off waivers be represented: known issue list, policy file, or both?
- Which report format is mandatory for formal DQA handoff: HTML, DOCX, XLSX, or all three?
