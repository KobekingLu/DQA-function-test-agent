# DQA Live Checks

This folder contains small, demo-friendly scripts for collecting real evidence
from a reachable Linux DUT.

The goal is not to replace the existing DQA tools. The goal is to create a
cleaner path for:

- quick function-test evidence collection
- repeatable smoke validation
- JSON output that the DQA demo agent can parse later

## Scripts

- `dqa_function_collect.py`
  - Read-only snapshot collector
  - Captures BIOS, CPU, memory, storage, network, PCIe, USB, and optional BMC
    evidence
  - Writes raw command output and a structured `evidence.json`

- `dqa_function_quick_check.py`
  - Optional active checks
  - Supports preflight readiness, memory stress, file-based storage smoke test,
    iperf3 external network test, and loopback-pair iperf3 test
  - Writes `quick_check.json` and per-test logs
  - When a required tool is missing, the result is `BLOCKED` or `SKIP` with an
    install hint
  - Can optionally install missing apt packages when the executor explicitly
    allows it

- `dqa_remote_run.py`
  - Reads a local JSON config with DUT SSH connection settings
  - Uploads the live-check scripts to the DUT
  - Runs the collector and optional quick checks remotely
  - Downloads JSON outputs and raw logs back to this workspace

## Suggested Usage

Run directly on the Linux DUT after SSH login:

```bash
python3 dqa_function_collect.py --label sky-721e3-evt
python3 dqa_function_quick_check.py --label sky-721e3-evt --preflight-only
python3 dqa_function_quick_check.py --label sky-721e3-evt --memory-seconds 300 --storage-dir /var/tmp
```

The local `preflight-only` run automatically inventories physical network
interfaces. You do not need to provide interface names just to discover NICs,
link state, speed, IPv4 addresses, or the default-route interface.

If you have an iperf3 server:

```bash
python3 dqa_function_quick_check.py \
  --label sky-721e3-evt \
  --network-server 192.168.1.20 \
  --network-seconds 20
```

Run from this Windows workspace through SSH:

```bash
python Script/dqa_live_checks/dqa_remote_run.py ^
  --config config/target_system.local.json ^
  --collect-only
```

Or run collector plus quick checks:

```bash
python Script/dqa_live_checks/dqa_remote_run.py ^
  --config config/target_system.local.json ^
  --memory-seconds 300 ^
  --storage-dir /var/tmp
```

Run setup readiness only:

```bash
python Script/dqa_live_checks/dqa_remote_run.py ^
  --config config/target_system.local.json ^
  --preflight-only
```

Preflight checks the tools and interfaces needed for the selected active checks.
If missing packages should be installed, add `--install-missing`; the local
runner asks for `Y` before the DUT is changed:

```bash
python Script/dqa_live_checks/dqa_remote_run.py ^
  --config config/target_system.local.json ^
  --preflight-only ^
  --install-missing
```

Installation requires DUT network or package-mirror access and root or
passwordless sudo permission. Use `--yes` only for automation after accepting
that risk. Automatic install currently targets Ubuntu/Debian-like systems with
`apt-get`; on other Linux distributions, install missing tools manually and
rerun preflight.

By default the remote runner also uses automatic network inventory. To make
specific interface names or loopback pairs hard requirements, set
`network_topology.mode` to `configured` in the local target config or pass
`--use-configured-network-topology`.

## Output Shape

Each run creates a timestamped folder under `output/` by default.

Example:

```text
output/
  sky-721e3-evt_20260410_141533/
    evidence.json
    summary.txt
    commands/
      001_hostname.txt
      002_uname.txt
      ...
```

## Mapping to Current DQA Function Work

Good first-pass coverage:

- `3.01` OS / driver install evidence
- `3.02` Memory inventory and optional memory stress
- `3.03` USB presence and topology evidence
- `3.04` / `3.05` Storage inventory and file-based smoke evidence
- `3.06` Ethernet inventory and optional iperf3 check
- `3.08` Buttons / indicators related software-side context is still manual
- `3.09` / `3.10` / `3.17` BMC or sensor evidence when `ipmitool` is present
- `4.01` RTC still needs a longer-duration procedure outside these scripts

## Notes

- The collector is intentionally read-only.
- The quick check avoids raw-disk writes; storage smoke uses a temp file.
- Some commands need root for full output, such as `dmidecode`, `journalctl`,
  `ipmitool`, or `smartctl`.
- Missing tools are reported as `SKIP`, not hard failure.
- `quick_check.json` now includes a `preflight` section with missing tools,
  interface readiness, and cable hints.
- Real credentials should live in `config/*.local.json`, which is ignored by git.
- If a command is usable on the DUT but not visible in non-interactive SSH
  discovery, you can add it to `assume_tools` in the target config.
- You can record DUT-specific cabling or port roles in `network_topology`
  inside the target config when active loopback or external-port checks need
  known physical wiring. Discovery-only preflight does not require this.
- Loopback iperf temporarily adds and removes IPv4 addresses on the specified
  pair. If either interface already has IPv4 configured, the test is skipped.
