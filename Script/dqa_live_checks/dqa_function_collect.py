#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CommandSpec:
    name: str
    command: str
    timeout: int = 30
    required_tools: tuple[str, ...] = ()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect DQA function-test evidence from a Linux DUT."
    )
    parser.add_argument(
        "--label",
        default="dut",
        help="Short run label used in the output folder name.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Base output directory. Default: ./output",
    )
    parser.add_argument(
        "--include-dmesg",
        action="store_true",
        help="Capture full dmesg output in addition to the error-focused views.",
    )
    parser.add_argument(
        "--assume-tool",
        action="append",
        default=[],
        help="Force a tool to be treated as available. Repeatable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"{sanitize_label(args.label)}_{timestamp}"
    commands_dir = run_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    tools = discover_tools(set(args.assume_tool))
    summary: dict[str, Any] = {
        "label": args.label,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "host": {
            "hostname": run_local_text("hostname").strip() or "unknown",
            "cwd": os.getcwd(),
            "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "",
        },
        "tool_availability": tools,
        "commands": [],
        "snapshot": {},
        "notes": [],
    }

    commands = build_command_list(include_dmesg=args.include_dmesg, tools=tools)
    outputs: dict[str, str] = {}

    for index, spec in enumerate(commands, start=1):
        result = run_command(spec)
        file_name = f"{index:03}_{spec.name}.txt"
        output_path = commands_dir / file_name
        output_path.write_text(result["combined_output"], encoding="utf-8")

        summary["commands"].append(
            {
                "name": spec.name,
                "command": spec.command,
                "returncode": result["returncode"],
                "timed_out": result["timed_out"],
                "output_file": str(output_path),
                "status": result["status"],
            }
        )
        outputs[spec.name] = result["stdout"]

    summary["snapshot"] = build_snapshot(outputs, tools)
    summary["notes"] = build_notes(summary["commands"], tools)

    evidence_path = run_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "summary.txt").write_text(render_summary(summary), encoding="utf-8")

    print(f"Evidence saved to {evidence_path}")
    return 0


def discover_tools(forced_tools: set[str]) -> dict[str, bool]:
    names = [
        "dmidecode",
        "dmesg",
        "ethtool",
        "free",
        "ip",
        "ipmitool",
        "journalctl",
        "lsblk",
        "lscpu",
        "lspci",
        "lsusb",
        "nvme",
        "ras-mc-ctl",
        "smartctl",
        "ss",
        "uptime",
    ]
    availability = {name: shutil.which(name) is not None for name in names}
    for name in forced_tools:
        availability[name] = True
    return availability


def build_command_list(*, include_dmesg: bool, tools: dict[str, bool]) -> list[CommandSpec]:
    specs = [
        CommandSpec("hostname", "hostname"),
        CommandSpec("date_iso", "date -Is"),
        CommandSpec("uname", "uname -a"),
        CommandSpec("os_release", "cat /etc/os-release"),
        CommandSpec("uptime", "uptime", required_tools=("uptime",)),
        CommandSpec("proc_cmdline", "cat /proc/cmdline"),
        CommandSpec("lscpu", "lscpu", required_tools=("lscpu",)),
        CommandSpec("free_m", "free -m", required_tools=("free",)),
        CommandSpec("lsblk_json", "lsblk -J -o NAME,KNAME,PATH,TYPE,SIZE,MODEL,SERIAL,ROTA,TRAN,MOUNTPOINTS,FSTYPE", required_tools=("lsblk",)),
        CommandSpec("ip_link_json", "ip -j link", required_tools=("ip",)),
        CommandSpec("ip_addr_json", "ip -j addr", required_tools=("ip",)),
        CommandSpec("ip_route", "ip route", required_tools=("ip",)),
        CommandSpec("ss_listen", "ss -tulpn", required_tools=("ss",)),
        CommandSpec("journal_boot_errors", "journalctl -b -p err..alert -n 200", required_tools=("journalctl",), timeout=45),
        CommandSpec("dmesg_error_scan", r"""python3 - <<'PY'
import re
import subprocess
patterns = re.compile(r"error|fail|timeout|mce|aer|ecc|edac", re.I)
proc = subprocess.run(["dmesg"], capture_output=True, text=True)
lines = [line for line in proc.stdout.splitlines() if patterns.search(line)]
print("\n".join(lines[-200:]))
PY""", required_tools=("dmesg",), timeout=45),
        CommandSpec("dmidecode_system", "dmidecode -t system", required_tools=("dmidecode",), timeout=45),
        CommandSpec("dmidecode_bios", "dmidecode -t bios", required_tools=("dmidecode",), timeout=45),
        CommandSpec("dmidecode_memory", "dmidecode -t memory", required_tools=("dmidecode",), timeout=60),
        CommandSpec("lspci_nn", "lspci -nn", required_tools=("lspci",), timeout=45),
        CommandSpec("lsusb", "lsusb", required_tools=("lsusb",)),
        CommandSpec("nvme_list_json", "nvme list -o json", required_tools=("nvme",), timeout=45),
        CommandSpec("smartctl_scan_json", "smartctl --scan -j", required_tools=("smartctl",), timeout=45),
        CommandSpec("ipmitool_sensor", "ipmitool sensor", required_tools=("ipmitool",), timeout=45),
        CommandSpec("ipmitool_fru", "ipmitool fru", required_tools=("ipmitool",), timeout=45),
        CommandSpec("ras_errors", "ras-mc-ctl --errors", required_tools=("ras-mc-ctl",), timeout=45),
    ]

    if include_dmesg:
        specs.append(CommandSpec("dmesg_full", "dmesg", required_tools=("dmesg",), timeout=60))

    available = []
    for spec in specs:
        if spec.required_tools and not all(tools.get(name, False) for name in spec.required_tools):
            continue
        available.append(spec)

    interfaces = parse_interface_names(run_local_text("ip -j link") if tools.get("ip") else "[]")
    for iface in interfaces:
        if tools.get("ethtool"):
            available.append(
                CommandSpec(
                    f"ethtool_{iface}",
                    f"ethtool {shlex.quote(iface)}",
                    required_tools=("ethtool",),
                )
            )
            available.append(
                CommandSpec(
                    f"ethtool_i_{iface}",
                    f"ethtool -i {shlex.quote(iface)}",
                    required_tools=("ethtool",),
                )
            )

    for dev in parse_block_devices(run_local_text("lsblk -J -o NAME,PATH,TYPE" if tools.get("lsblk") else "echo '{}'")):
        if tools.get("smartctl"):
            quoted = shlex.quote(dev)
            available.append(
                CommandSpec(
                    f"smartctl_health_{Path(dev).name}",
                    f"smartctl -H -A {quoted}",
                    required_tools=("smartctl",),
                    timeout=45,
                )
            )

    return available


def run_command(spec: CommandSpec) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            spec.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=spec.timeout,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        return {
            "stdout": stdout,
            "stderr": stderr,
            "combined_output": combine_output(spec.command, stdout, stderr, completed.returncode, False),
            "returncode": completed.returncode,
            "timed_out": False,
            "status": "PASS" if completed.returncode == 0 else "WARN",
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return {
            "stdout": stdout,
            "stderr": stderr,
            "combined_output": combine_output(spec.command, stdout, stderr, -1, True),
            "returncode": -1,
            "timed_out": True,
            "status": "WARN",
        }


def combine_output(command: str, stdout: str, stderr: str, returncode: int, timed_out: bool) -> str:
    parts = [
        f"$ {command}",
        f"[returncode] {returncode}",
        f"[timed_out] {timed_out}",
        "",
        "[stdout]",
        stdout.rstrip(),
        "",
        "[stderr]",
        stderr.rstrip(),
        "",
    ]
    return "\n".join(parts)


def build_snapshot(outputs: dict[str, str], tools: dict[str, bool]) -> dict[str, Any]:
    os_release = parse_os_release(outputs.get("os_release", ""))
    lsblk_json = parse_json_text(outputs.get("lsblk_json", ""))
    ip_link_json = parse_json_text(outputs.get("ip_link_json", ""))
    ip_addr_json = parse_json_text(outputs.get("ip_addr_json", ""))
    nvme_json = parse_json_text(outputs.get("nvme_list_json", ""))
    smart_scan = parse_json_text(outputs.get("smartctl_scan_json", ""))

    block_devices = []
    if isinstance(lsblk_json, dict):
        for item in lsblk_json.get("blockdevices", []):
            if item.get("type") == "disk":
                block_devices.append(
                    {
                        "name": item.get("name"),
                        "path": item.get("path"),
                        "size": item.get("size"),
                        "model": item.get("model"),
                        "serial": item.get("serial"),
                        "transport": item.get("tran"),
                        "mountpoints": item.get("mountpoints"),
                    }
                )

    interfaces = merge_interfaces(ip_link_json, ip_addr_json)

    storage_health = []
    for name, output in outputs.items():
        if name.startswith("smartctl_health_"):
            storage_health.append(parse_smartctl_health(name, output))

    snapshot: dict[str, Any] = {
        "system": {
            "kernel": outputs.get("uname", "").strip(),
            "os_release": os_release,
            "uptime": outputs.get("uptime", "").strip(),
            "cmdline": outputs.get("proc_cmdline", "").strip(),
        },
        "hardware": {
            "cpu_summary": outputs.get("lscpu", "").strip(),
            "memory_summary": outputs.get("free_m", "").strip(),
            "bios_summary": extract_dmidecode_field(outputs.get("dmidecode_bios", ""), "Version"),
            "product_name": extract_dmidecode_field(outputs.get("dmidecode_system", ""), "Product Name"),
        },
        "network": {
            "interfaces": interfaces,
            "routes": outputs.get("ip_route", "").strip().splitlines(),
        },
        "storage": {
            "block_devices": block_devices,
            "nvme": nvme_json,
            "smart_scan": smart_scan,
            "health_checks": storage_health,
        },
        "usb": {
            "device_lines": outputs.get("lsusb", "").strip().splitlines(),
        },
        "pcie": {
            "device_lines": outputs.get("lspci_nn", "").strip().splitlines(),
        },
        "bmc": {
            "supported": tools.get("ipmitool", False),
            "sensor_excerpt": outputs.get("ipmitool_sensor", "").strip().splitlines()[:30],
            "fru_excerpt": outputs.get("ipmitool_fru", "").strip().splitlines()[:30],
        },
        "boot": {
            "journal_error_lines": outputs.get("journal_boot_errors", "").strip().splitlines(),
            "dmesg_error_lines": outputs.get("dmesg_error_scan", "").strip().splitlines(),
        },
    }
    return snapshot


def build_notes(commands: list[dict[str, Any]], tools: dict[str, bool]) -> list[str]:
    notes: list[str] = []
    missing = [name for name, present in tools.items() if not present]
    if missing:
        notes.append(f"Missing tools were skipped: {', '.join(sorted(missing))}.")
    warned = [item["name"] for item in commands if item["status"] != "PASS"]
    if warned:
        notes.append(f"Some commands need review: {', '.join(warned)}.")
    if not warned and not missing:
        notes.append("All selected evidence commands completed without command-level warnings.")
    return notes


def render_summary(summary: dict[str, Any]) -> str:
    snap = summary["snapshot"]
    lines = [
        f"Label: {summary['label']}",
        f"Collected at: {summary['collected_at']}",
        f"Hostname: {summary['host']['hostname']}",
        f"Product: {snap['hardware'].get('product_name', '')}",
        f"BIOS: {snap['hardware'].get('bios_summary', '')}",
        f"Interfaces: {len(snap['network'].get('interfaces', []))}",
        f"Block devices: {len(snap['storage'].get('block_devices', []))}",
        f"SMART checks: {len(snap['storage'].get('health_checks', []))}",
        "",
        "Notes:",
    ]
    lines.extend(f"- {note}" for note in summary.get("notes", []))
    return "\n".join(lines) + "\n"


def parse_os_release(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value.strip().strip('"')
    return result


def parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def extract_dmidecode_field(text: str, field_name: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(field_name)}:\s*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def parse_interface_names(text: str) -> list[str]:
    data = parse_json_text(text)
    names: list[str] = []
    if isinstance(data, list):
        for item in data:
            name = item.get("ifname")
            if not name or name == "lo":
                continue
            names.append(str(name))
    return names


def parse_block_devices(text: str) -> list[str]:
    data = parse_json_text(text)
    devices: list[str] = []
    if isinstance(data, dict):
        for item in data.get("blockdevices", []):
            if item.get("type") == "disk" and item.get("path"):
                devices.append(str(item["path"]))
    return devices


def merge_interfaces(link_data: Any, addr_data: Any) -> list[dict[str, Any]]:
    addr_map: dict[str, list[str]] = {}
    if isinstance(addr_data, list):
        for item in addr_data:
            name = item.get("ifname")
            if not name:
                continue
            addrs = []
            for info in item.get("addr_info", []):
                local = info.get("local")
                if local:
                    addrs.append(str(local))
            addr_map[str(name)] = addrs

    merged: list[dict[str, Any]] = []
    if isinstance(link_data, list):
        for item in link_data:
            name = item.get("ifname")
            if not name or name == "lo":
                continue
            merged.append(
                {
                    "ifname": name,
                    "operstate": item.get("operstate"),
                    "mtu": item.get("mtu"),
                    "mac": item.get("address"),
                    "addresses": addr_map.get(str(name), []),
                }
            )
    return merged


def parse_smartctl_health(command_name: str, output: str) -> dict[str, Any]:
    device = command_name.removeprefix("smartctl_health_")
    passed = ""
    match = re.search(r"SMART overall-health self-assessment test result:\s*(.+)", output, re.I)
    if not match:
        match = re.search(r"SMART Health Status:\s*(.+)", output, re.I)
    if match:
        passed = match.group(1).strip()
    return {
        "device": device,
        "health_result": passed,
        "contains_error_keyword": bool(re.search(r"fail|error", output, re.I)),
    }


def sanitize_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", label.strip())
    return cleaned or "dut"


def run_local_text(command: str) -> str:
    completed = subprocess.run(command, shell=True, capture_output=True, text=True)
    return completed.stdout or ""


if __name__ == "__main__":
    raise SystemExit(main())
