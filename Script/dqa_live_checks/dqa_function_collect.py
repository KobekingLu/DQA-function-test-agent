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
    summary["info_index"] = build_info_index(summary["snapshot"], summary["commands"], tools)
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
        "df",
        "findmnt",
        "free",
        "hostnamectl",
        "ip",
        "ipmitool",
        "journalctl",
        "lsblk",
        "lscpu",
        "lsmem",
        "lsmod",
        "lspci",
        "lsusb",
        "nvme",
        "ras-mc-ctl",
        "smartctl",
        "ss",
        "systemctl",
        "timedatectl",
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
        CommandSpec("hostnamectl", "hostnamectl", required_tools=("hostnamectl",)),
        CommandSpec("timedatectl", "timedatectl", required_tools=("timedatectl",)),
        CommandSpec("os_release", "cat /etc/os-release"),
        CommandSpec("uptime", "uptime", required_tools=("uptime",)),
        CommandSpec("proc_cmdline", "cat /proc/cmdline"),
        CommandSpec("lscpu", "lscpu", required_tools=("lscpu",)),
        CommandSpec("lscpu_json", "lscpu -J", required_tools=("lscpu",)),
        CommandSpec("lsmem", "lsmem", required_tools=("lsmem",)),
        CommandSpec("free_m", "free -m", required_tools=("free",)),
        CommandSpec("lsblk_json", "lsblk -J -o NAME,KNAME,PATH,TYPE,SIZE,MODEL,SERIAL,ROTA,TRAN,MOUNTPOINTS,FSTYPE", required_tools=("lsblk",)),
        CommandSpec("lsblk_fs_json", "lsblk -J -f", required_tools=("lsblk",)),
        CommandSpec("df_h", "df -hT -x tmpfs -x devtmpfs", required_tools=("df",)),
        CommandSpec("findmnt_json", "findmnt -J -D", required_tools=("findmnt",)),
        CommandSpec("ip_link_json", "ip -j link", required_tools=("ip",)),
        CommandSpec("ip_addr_json", "ip -j addr", required_tools=("ip",)),
        CommandSpec("ip_route", "ip route", required_tools=("ip",)),
        CommandSpec("ss_listen", "ss -tulpn", required_tools=("ss",)),
        CommandSpec("systemd_failed", "systemctl --failed --no-pager --plain", required_tools=("systemctl",), timeout=45),
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
        CommandSpec("dmidecode_baseboard", "dmidecode -t baseboard", required_tools=("dmidecode",), timeout=45),
        CommandSpec("dmidecode_chassis", "dmidecode -t chassis", required_tools=("dmidecode",), timeout=45),
        CommandSpec("dmidecode_processor", "dmidecode -t processor", required_tools=("dmidecode",), timeout=60),
        CommandSpec("dmidecode_memory", "dmidecode -t memory", required_tools=("dmidecode",), timeout=60),
        CommandSpec("lspci_nn", "lspci -nn", required_tools=("lspci",), timeout=45),
        CommandSpec("lspci_tree", "lspci -tv", required_tools=("lspci",), timeout=45),
        CommandSpec("lspci_kernel", "lspci -k -nn", required_tools=("lspci",), timeout=60),
        CommandSpec("lsmod", "lsmod", required_tools=("lsmod",), timeout=45),
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
        if tools.get("nvme") and Path(dev).name.startswith("nvme"):
            quoted = shlex.quote(dev)
            available.append(
                CommandSpec(
                    f"nvme_smart_log_{Path(dev).name}",
                    f"nvme smart-log {quoted} -o json",
                    required_tools=("nvme",),
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
    lscpu_map = parse_lscpu(outputs.get("lscpu", ""), outputs.get("lscpu_json", ""))
    lsblk_json = parse_json_text(outputs.get("lsblk_json", ""))
    lsblk_fs_json = parse_json_text(outputs.get("lsblk_fs_json", ""))
    findmnt_json = parse_json_text(outputs.get("findmnt_json", ""))
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

    interfaces = enrich_interfaces(merge_interfaces(ip_link_json, ip_addr_json), outputs)

    storage_health = []
    nvme_health = []
    for name, output in outputs.items():
        if name.startswith("smartctl_health_"):
            storage_health.append(parse_smartctl_health(name, output))
        elif name.startswith("nvme_smart_log_"):
            nvme_health.append(parse_nvme_smart_log(name, output))

    dmi_system = parse_dmidecode_key_values(outputs.get("dmidecode_system", ""))
    dmi_bios = parse_dmidecode_key_values(outputs.get("dmidecode_bios", ""))
    dmi_baseboard = parse_dmidecode_key_values(outputs.get("dmidecode_baseboard", ""))
    dmi_chassis = parse_dmidecode_key_values(outputs.get("dmidecode_chassis", ""))
    processors = parse_processor_inventory(outputs.get("dmidecode_processor", ""))
    memory_inventory = parse_memory_inventory(
        outputs.get("dmidecode_memory", ""),
        outputs.get("free_m", ""),
        outputs.get("lsmem", ""),
    )
    pcie_devices = parse_lspci_devices(outputs.get("lspci_nn", ""))
    usb_lines = outputs.get("lsusb", "").strip().splitlines()
    journal_errors = outputs.get("journal_boot_errors", "").strip().splitlines()
    dmesg_errors = outputs.get("dmesg_error_scan", "").strip().splitlines()

    snapshot: dict[str, Any] = {
        "system": {
            "hostname": outputs.get("hostname", "").strip(),
            "kernel": outputs.get("uname", "").strip(),
            "os_release": os_release,
            "hostnamectl": parse_colon_lines(outputs.get("hostnamectl", "")),
            "time": parse_colon_lines(outputs.get("timedatectl", "")),
            "uptime": outputs.get("uptime", "").strip(),
            "cmdline": outputs.get("proc_cmdline", "").strip(),
            "failed_services": parse_systemd_failed(outputs.get("systemd_failed", "")),
        },
        "hardware": {
            "cpu_summary": outputs.get("lscpu", "").strip(),
            "memory_summary": outputs.get("free_m", "").strip(),
            "bios_summary": dmi_bios.get("Version", ""),
            "product_name": dmi_system.get("Product Name", ""),
            "system": dmi_system,
            "bios": dmi_bios,
            "baseboard": dmi_baseboard,
            "chassis": dmi_chassis,
        },
        "cpu": {
            "architecture": lscpu_map.get("Architecture", ""),
            "model_name": lscpu_map.get("Model name", ""),
            "vendor": lscpu_map.get("Vendor ID", ""),
            "cpu_count": to_int(lscpu_map.get("CPU(s)", "")),
            "socket_count": to_int(lscpu_map.get("Socket(s)", "")),
            "cores_per_socket": to_int(lscpu_map.get("Core(s) per socket", "")),
            "threads_per_core": to_int(lscpu_map.get("Thread(s) per core", "")),
            "numa_nodes": to_int(lscpu_map.get("NUMA node(s)", "")),
            "virtualization": lscpu_map.get("Virtualization", ""),
            "cache": {
                "l1d": lscpu_map.get("L1d cache", ""),
                "l1i": lscpu_map.get("L1i cache", ""),
                "l2": lscpu_map.get("L2 cache", ""),
                "l3": lscpu_map.get("L3 cache", ""),
            },
            "processors": processors,
        },
        "memory": memory_inventory,
        "filesystems": {
            "df": parse_df_table(outputs.get("df_h", "")),
            "mounts": parse_findmnt(findmnt_json),
        },
        "network": {
            "interfaces": interfaces,
            "routes": outputs.get("ip_route", "").strip().splitlines(),
            "default_route_interfaces": default_route_interfaces(outputs.get("ip_route", "")),
            "listening_ports": summarize_listening_ports(outputs.get("ss_listen", "")),
        },
        "storage": {
            "block_devices": block_devices,
            "filesystems": simplify_lsblk_filesystems(lsblk_fs_json),
            "nvme": nvme_json,
            "nvme_health": nvme_health,
            "smart_scan": smart_scan,
            "health_checks": storage_health,
        },
        "usb": {
            "device_count": len(usb_lines),
            "device_lines": usb_lines,
        },
        "pcie": {
            "device_count": len(pcie_devices),
            "class_summary": summarize_pcie_classes(pcie_devices),
            "devices": pcie_devices,
            "tree": outputs.get("lspci_tree", "").strip().splitlines(),
            "kernel_driver_lines": outputs.get("lspci_kernel", "").strip().splitlines(),
        },
        "bmc": {
            "supported": tools.get("ipmitool", False),
            "sensor_summary": summarize_ipmi_sensors(outputs.get("ipmitool_sensor", "")),
            "sensor_excerpt": outputs.get("ipmitool_sensor", "").strip().splitlines()[:30],
            "fru": parse_ipmi_fru(outputs.get("ipmitool_fru", "")),
            "fru_excerpt": outputs.get("ipmitool_fru", "").strip().splitlines()[:30],
        },
        "boot": {
            "journal_error_count": len(journal_errors),
            "journal_error_lines": journal_errors,
            "dmesg_error_count": len(dmesg_errors),
            "dmesg_error_lines": dmesg_errors,
            "ras_errors": outputs.get("ras_errors", "").strip().splitlines(),
        },
        "kernel": {
            "loaded_module_count": count_lsmod_modules(outputs.get("lsmod", "")),
        },
    }
    snapshot["info_quality"] = build_snapshot_quality(snapshot, tools)
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
    cpu = snap.get("cpu", {})
    memory = snap.get("memory", {})
    network = snap.get("network", {})
    pcie = snap.get("pcie", {})
    boot = snap.get("boot", {})
    quality = snap.get("info_quality", {})
    lines = [
        f"Label: {summary['label']}",
        f"Collected at: {summary['collected_at']}",
        f"Hostname: {summary['host']['hostname']}",
        f"Product: {snap['hardware'].get('product_name', '')}",
        f"BIOS: {snap['hardware'].get('bios_summary', '')}",
        f"CPU: {cpu.get('model_name', '')}",
        f"CPU topology: sockets={cpu.get('socket_count')} cores/socket={cpu.get('cores_per_socket')} threads/core={cpu.get('threads_per_core')} logical={cpu.get('cpu_count')}",
        f"Memory slots: populated={memory.get('populated_slot_count')} empty={memory.get('empty_slot_count')} total={memory.get('slot_count')}",
        f"Interfaces: {len(network.get('interfaces', []))}",
        f"Default route interfaces: {', '.join(network.get('default_route_interfaces', [])) or 'none'}",
        f"Block devices: {len(snap['storage'].get('block_devices', []))}",
        f"SMART checks: {len(snap['storage'].get('health_checks', []))}",
        f"PCIe devices: {pcie.get('device_count', 0)} {pcie.get('class_summary', {})}",
        f"USB devices: {snap.get('usb', {}).get('device_count', 0)}",
        f"Boot journal errors: {boot.get('journal_error_count', 0)}",
        f"dmesg error keywords: {boot.get('dmesg_error_count', 0)}",
        f"Info quality warnings: {quality.get('warning_count', 0)}",
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


def parse_lscpu(text: str, json_text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    data = parse_json_text(json_text)
    if isinstance(data, dict):
        for item in data.get("lscpu", []):
            field = str(item.get("field", "")).rstrip(":").strip()
            value = str(item.get("data", "")).strip()
            if field:
                parsed[field] = value
    if parsed:
        return parsed

    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def parse_colon_lines(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def parse_systemd_failed(text: str) -> list[dict[str, str]]:
    services = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("UNIT ") or stripped.startswith("LOAD "):
            continue
        parts = stripped.split(None, 4)
        if len(parts) >= 4 and parts[1] in {"loaded", "not-found", "masked"}:
            services.append(
                {
                    "unit": parts[0],
                    "load": parts[1],
                    "active": parts[2],
                    "sub": parts[3],
                    "description": parts[4] if len(parts) > 4 else "",
                }
            )
    return services


def to_int(value: object) -> int | None:
    match = re.search(r"-?[0-9]+", str(value))
    return int(match.group(0)) if match else None


def parse_dmidecode_key_values(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        if not line.startswith(("\t", " ")):
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in parsed:
            parsed[key] = value
    return parsed


def parse_dmidecode_records(text: str, title: str) -> list[dict[str, str]]:
    records = []
    current: dict[str, str] | None = None
    in_record = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == title:
            current = {}
            records.append(current)
            in_record = True
            continue
        if stripped.startswith("Handle ") and in_record:
            current = None
            in_record = False
            continue
        if current is not None and ":" in line and line.startswith(("\t", " ")):
            key, value = line.split(":", 1)
            current[key.strip()] = value.strip()
    return records


def parse_processor_inventory(text: str) -> list[dict[str, str]]:
    processors = []
    for record in parse_dmidecode_records(text, "Processor Information"):
        populated = record.get("Status", "").lower()
        processors.append(
            {
                "socket": record.get("Socket Designation", ""),
                "manufacturer": record.get("Manufacturer", ""),
                "version": record.get("Version", ""),
                "status": record.get("Status", ""),
                "core_count": record.get("Core Count", ""),
                "thread_count": record.get("Thread Count", ""),
                "current_speed": record.get("Current Speed", ""),
                "populated": "populated" in populated or "enabled" in populated,
            }
        )
    return processors


def parse_memory_inventory(dmidecode_text: str, free_text: str, lsmem_text: str) -> dict[str, Any]:
    devices = []
    for record in parse_dmidecode_records(dmidecode_text, "Memory Device"):
        size = record.get("Size", "")
        populated = bool(size and "no module installed" not in size.lower())
        devices.append(
            {
                "locator": record.get("Locator", ""),
                "bank_locator": record.get("Bank Locator", ""),
                "size": size,
                "type": record.get("Type", ""),
                "speed": record.get("Speed", ""),
                "configured_speed": record.get("Configured Memory Speed", ""),
                "manufacturer": record.get("Manufacturer", ""),
                "part_number": record.get("Part Number", ""),
                "serial_number": record.get("Serial Number", ""),
                "populated": populated,
            }
        )

    return {
        "os_summary": parse_free_summary(free_text),
        "range_summary": parse_lsmem_summary(lsmem_text),
        "slot_count": len(devices),
        "populated_slot_count": sum(1 for item in devices if item["populated"]),
        "empty_slot_count": sum(1 for item in devices if not item["populated"]),
        "devices": devices,
    }


def parse_free_summary(text: str) -> dict[str, str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return {}
    headers = lines[0].split()
    mem_values = lines[1].split()
    if mem_values and mem_values[0].rstrip(":").lower() == "mem":
        mem_values = mem_values[1:]
    return {key: value for key, value in zip(headers, mem_values)}


def parse_lsmem_summary(text: str) -> dict[str, str]:
    return parse_colon_lines(text)


def parse_df_table(text: str) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return []
    filesystems = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 7:
            continue
        filesystems.append(
            {
                "filesystem": parts[0],
                "type": parts[1],
                "size": parts[2],
                "used": parts[3],
                "available": parts[4],
                "use_percent": parts[5],
                "mounted_on": " ".join(parts[6:]),
            }
        )
    return filesystems


def parse_findmnt(data: Any) -> list[dict[str, str]]:
    if not isinstance(data, dict):
        return []
    filesystems = []

    def visit(items: list[dict[str, Any]]) -> None:
        for item in items:
            filesystems.append(
                {
                    "target": str(item.get("target", "")),
                    "source": str(item.get("source", "")),
                    "fstype": str(item.get("fstype", "")),
                    "size": str(item.get("size", "")),
                    "used": str(item.get("used", "")),
                    "avail": str(item.get("avail", "")),
                    "use_percent": str(item.get("use%", "")),
                }
            )
            children = item.get("children", [])
            if isinstance(children, list):
                visit(children)

    visit(data.get("filesystems", []))
    return filesystems


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


def enrich_interfaces(interfaces: list[dict[str, Any]], outputs: dict[str, str]) -> list[dict[str, Any]]:
    enriched = []
    for item in interfaces:
        iface = str(item.get("ifname", ""))
        ethtool = parse_ethtool(outputs.get(f"ethtool_{iface}", ""))
        driver = parse_ethtool_driver(outputs.get(f"ethtool_i_{iface}", ""))
        merged = dict(item)
        merged.update(
            {
                "link_detected": ethtool.get("Link detected", ""),
                "speed": ethtool.get("Speed", ""),
                "duplex": ethtool.get("Duplex", ""),
                "auto_negotiation": ethtool.get("Auto-negotiation", ""),
                "driver": driver.get("driver", ""),
                "driver_version": driver.get("version", ""),
                "firmware_version": driver.get("firmware-version", ""),
                "bus_info": driver.get("bus-info", ""),
            }
        )
        enriched.append(merged)
    return enriched


def parse_ethtool(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"Speed", "Duplex", "Auto-negotiation", "Link detected", "Port"}:
            parsed[key] = value.strip()
    return parsed


def parse_ethtool_driver(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"driver", "version", "firmware-version", "bus-info"}:
            parsed[key] = value.strip()
    return parsed


def default_route_interfaces(route_text: str) -> list[str]:
    interfaces = []
    for line in route_text.splitlines():
        if not line.startswith("default"):
            continue
        match = re.search(r"\bdev\s+(\S+)", line)
        if match:
            interfaces.append(match.group(1))
    return sorted(set(interfaces))


def summarize_listening_ports(text: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith(("tcp", "udp")):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        rows.append(
            {
                "protocol": parts[0],
                "state": parts[1] if parts[0] == "tcp" else "",
                "local_address": parts[4] if parts[0] == "tcp" and len(parts) > 4 else parts[3],
                "process": " ".join(parts[6:]) if len(parts) > 6 else "",
            }
        )
    return rows[:50]


def simplify_lsblk_filesystems(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    simplified = []

    def visit(items: list[dict[str, Any]]) -> None:
        for item in items:
            simplified.append(
                {
                    "name": item.get("name"),
                    "fstype": item.get("fstype"),
                    "fsver": item.get("fsver"),
                    "label": item.get("label"),
                    "uuid": item.get("uuid"),
                    "mountpoints": item.get("mountpoints"),
                }
            )
            children = item.get("children", [])
            if isinstance(children, list):
                visit(children)

    visit(data.get("blockdevices", []))
    return simplified


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


def parse_nvme_smart_log(command_name: str, output: str) -> dict[str, Any]:
    device = command_name.removeprefix("nvme_smart_log_")
    data = parse_json_text(output)
    if not isinstance(data, dict):
        return {"device": device, "parsed": False}
    return {
        "device": device,
        "parsed": True,
        "critical_warning": data.get("critical_warning"),
        "temperature": data.get("temperature"),
        "available_spare": data.get("avail_spare") or data.get("available_spare"),
        "percentage_used": data.get("percent_used") or data.get("percentage_used"),
        "power_on_hours": data.get("power_on_hours"),
        "unsafe_shutdowns": data.get("unsafe_shutdowns"),
        "media_errors": data.get("media_errors"),
        "num_err_log_entries": data.get("num_err_log_entries"),
    }


def parse_lspci_devices(text: str) -> list[dict[str, str]]:
    devices = []
    pattern = re.compile(r"^(?P<slot>[0-9a-fA-F:.]+)\s+(?P<class>.+?):\s+(?P<device>.+)$")
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        device_text = match.group("device")
        ids = re.findall(r"\[([0-9a-fA-F]{4}:[0-9a-fA-F]{4})\]", device_text)
        devices.append(
            {
                "slot": match.group("slot"),
                "class": match.group("class"),
                "category": classify_pcie_device(match.group("class"), device_text),
                "device": device_text,
                "pci_id": ids[-1] if ids else "",
            }
        )
    return devices


def classify_pcie_device(device_class: str, device_text: str) -> str:
    text = f"{device_class} {device_text}".lower()
    if "ethernet" in text or "network" in text:
        return "network"
    if "non-volatile memory" in text or "sata" in text or "raid" in text or "storage" in text:
        return "storage"
    if "vga" in text or "3d controller" in text or "display" in text:
        return "graphics"
    if "usb" in text:
        return "usb"
    if "bridge" in text:
        return "bridge"
    if "qat" in text or "quickassist" in text:
        return "accelerator"
    return "other"


def summarize_pcie_classes(devices: list[dict[str, str]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in devices:
        category = item.get("category", "other")
        summary[category] = summary.get(category, 0) + 1
    return dict(sorted(summary.items()))


def summarize_ipmi_sensors(text: str) -> dict[str, Any]:
    lines = [line for line in text.splitlines() if "|" in line]
    non_ok = []
    for line in lines:
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 4:
            continue
        status = parts[3].lower()
        if status not in {"ok", "na", "ns", "0x0000", "0x0100", ""}:
            non_ok.append({"sensor": parts[0], "reading": parts[1], "status": parts[3]})
    return {
        "sensor_count": len(lines),
        "non_ok_count": len(non_ok),
        "non_ok_excerpt": non_ok[:20],
    }


def parse_ipmi_fru(text: str) -> dict[str, str]:
    wanted = {
        "Board Mfg",
        "Board Product",
        "Board Serial",
        "Board Part Number",
        "Product Manufacturer",
        "Product Name",
        "Product Part Number",
        "Product Serial",
    }
    parsed = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in wanted and key not in parsed:
            parsed[key] = value.strip()
    return parsed


def count_lsmod_modules(text: str) -> int:
    return max(0, len([line for line in text.splitlines() if line.strip()]) - 1)


def build_snapshot_quality(snapshot: dict[str, Any], tools: dict[str, bool]) -> dict[str, Any]:
    missing_tools = sorted(name for name, present in tools.items() if not present)
    warnings = []
    if missing_tools:
        warnings.append("Some optional evidence tools are missing.")
    if not snapshot.get("hardware", {}).get("product_name"):
        warnings.append("DMI product name is missing.")
    if not snapshot.get("network", {}).get("interfaces"):
        warnings.append("No network interfaces were parsed.")
    if snapshot.get("boot", {}).get("journal_error_count", 0):
        warnings.append("Boot journal contains error-level lines.")
    if snapshot.get("boot", {}).get("dmesg_error_count", 0):
        warnings.append("dmesg contains error/fail/timeout keywords.")
    return {
        "missing_tool_count": len(missing_tools),
        "missing_tools": missing_tools,
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def build_info_index(
    snapshot: dict[str, Any],
    commands: list[dict[str, Any]],
    tools: dict[str, bool],
) -> dict[str, Any]:
    command_warnings = [
        item["name"] for item in commands if item.get("status") != "PASS"
    ]
    return {
        "schema": "dqa.live_info.v2",
        "sections": {
            "system": bool(snapshot.get("system")),
            "hardware": bool(snapshot.get("hardware")),
            "cpu": bool(snapshot.get("cpu")),
            "memory": bool(snapshot.get("memory", {}).get("devices")),
            "storage": bool(snapshot.get("storage", {}).get("block_devices")),
            "network": bool(snapshot.get("network", {}).get("interfaces")),
            "pcie": bool(snapshot.get("pcie", {}).get("devices")),
            "usb": bool(snapshot.get("usb", {}).get("device_lines")),
            "bmc": bool(snapshot.get("bmc", {}).get("supported")),
            "boot_health": bool(snapshot.get("boot")),
        },
        "command_count": len(commands),
        "command_warning_count": len(command_warnings),
        "command_warnings": command_warnings,
        "missing_tools": sorted(name for name, present in tools.items() if not present),
        "legacy_info_coverage": [
            "cpu_info",
            "ram_info",
            "lan_info",
            "storage_info",
            "usb_info",
            "pcie_info",
            "sdr_info",
            "dmi",
        ],
    }


def sanitize_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", label.strip())
    return cleaned or "dut"


def run_local_text(command: str) -> str:
    completed = subprocess.run(command, shell=True, capture_output=True, text=True)
    return completed.stdout or ""


if __name__ == "__main__":
    raise SystemExit(main())
