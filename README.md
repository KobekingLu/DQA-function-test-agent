# DQA Function Test Review Agent

This repository is a DQA function-test review prototype and the starting point for a redesigned X86UniTest v2 platform.

The current project has two tracks:

- `function_test_agent/`: a runnable review agent that compares expected tests, actual results, and known issues.
- `x86unittest_v2/`: a new profile-driven skeleton for planning, collecting, reviewing, and exporting X86UniTest evidence.

The long-term goal is to make DQA function testing easier to run, explain, review, and hand off.

## What It Reviews

The review agent reads:

- expected test plan
- actual execution result
- known issue or waiver list

Then it explains:

- which tests were covered
- which tests passed, failed, or were blocked
- where evidence is missing
- why the recommendation was made
- who should own the next action

The supported recommendations are:

- `Ready for Exit`
- `Retest Required`
- `Block Release`

## Quick Start: Review Agent

```bash
python demo.py
```

Generated JSON and HTML outputs are written under `output/`.

## Quick Start: SSH DUT Evidence

Create a git-ignored local target config from the example:

```bash
cp config/target_system.example.json config/target_system.local.json
```

Update `config/target_system.local.json` with the DUT host, username, and lab-only
credential. Then run the safest remote check first:

```bash
python Script/dqa_live_checks/dqa_remote_run.py \
  --config config/target_system.local.json \
  --preflight-only
```

The runner uploads small Python scripts to the DUT, collects read-only evidence,
downloads JSON artifacts under `output/remote_runs/`, and lets `python demo.py`
include the latest live DUT review in the bilingual report.

The same scripts can run directly on the Linux DUT after SSH login:

```bash
python3 dqa_function_collect.py --label local-dut
python3 dqa_function_quick_check.py --label local-dut --preflight-only
```

Network preflight now performs automatic NIC inventory by default, so interface
names are not required for discovery. Configure `network_topology.mode` as
`configured` only when you want specific cabled ports or loopback pairs to become
hard requirements for active network checks.

The live collector now writes both raw command logs and structured info sections
for system, DMI, CPU, memory slots, storage, network, PCIe, USB, BMC, and boot
health. The `info_index` in `evidence.json` summarizes which sections were
collected and which legacy info areas are covered.

Use preflight to check required tools before enabling active checks. If a tool is
missing and you want the runner to install supported packages, add
`--install-missing`. The runner asks for `Y` confirmation because installation
requires DUT network or package-mirror access and root or passwordless sudo
permission:

```bash
python Script/dqa_live_checks/dqa_remote_run.py \
  --config config/target_system.local.json \
  --preflight-only \
  --install-missing
```

For automation, add `--yes` only when you already accept the DUT package changes.
Automatic install is currently intended for Ubuntu/Debian-like systems with
`apt-get`. Evidence collection and preflight are Linux-oriented and can still run
on other distributions when the required commands are available.

## Quick Start: X86UniTest v2 Skeleton

From the v2 source directory:

```bash
cd x86unittest_v2/src
python -B -m x86unittest.cli doctor --profile fwa6083
python -B -m x86unittest.cli plan --profile fwa6083
python -B -m x86unittest.cli run --profile fwa6083 --collect-only --output ../../output/v2_runs
python -B -m x86unittest.cli review --run ../../output/v2_runs/<run_id>
python -B -m x86unittest.cli export --run ../../output/v2_runs/<run_id>
```

On Windows, `doctor` is expected to report missing Linux DUT tools such as `lscpu`, `lsblk`, `ipmitool`, and `ethtool`. That is a readiness signal, not a crash.

## Repository Safety

This public-friendly tree intentionally excludes real DUT credentials, generated outputs, internal documents, debug logs, and legacy tool bundles.

Before publishing, check:

- `GITHUB_PUBLICATION_CHECKLIST.md`
- `.gitignore`
- `config/target_system.example.json`

Real SSH target files should be stored as `config/*.local.json`, which is ignored.

## Architecture

See `X86UNITEST_V2_ARCHITECTURE.md` for the v2 direction:

- Control Plane: CLI, profile, planning, run lifecycle, export
- Execution Plane: collectors, preflight, local or remote adapters, legacy shell bridge
- Review Plane: normalization, coverage, issue matching, decision, JSON and HTML reports

## Current Status

This is not yet a full replacement for legacy x86UniTest. The useful first slice is now in place:

- profile loading
- test pack registry
- preflight checks
- collect-only run folder creation
- canonical JSON artifacts
- bilingual HTML review
- ZIP export

Next step: wire the v2 remote adapter to the existing SSH live-check flow in `Script/dqa_live_checks/`.
