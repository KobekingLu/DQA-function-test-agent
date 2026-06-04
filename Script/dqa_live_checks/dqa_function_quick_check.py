#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run small active DQA function checks on a Linux DUT."
    )
    parser.add_argument("--label", default="dut", help="Run label.")
    parser.add_argument("--output-dir", default="output", help="Base output directory.")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Collect setup readiness only. Do not run active tests.",
    )
    parser.add_argument(
        "--install-missing",
        action="store_true",
        help="Install missing packages for requested checks when the DUT OS supports it.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm package installation without an interactive prompt.",
    )
    parser.add_argument(
        "--memory-seconds",
        type=int,
        default=0,
        help="Run stress-ng memory test for N seconds. 0 disables the test.",
    )
    parser.add_argument(
        "--storage-dir",
        default="",
        help="Directory for file-based storage smoke test. Empty disables the test.",
    )
    parser.add_argument(
        "--storage-mb",
        type=int,
        default=512,
        help="How many MiB to write and read during the storage smoke test.",
    )
    parser.add_argument(
        "--network-server",
        default="",
        help="iperf3 server address. Empty disables the network test.",
    )
    parser.add_argument(
        "--network-seconds",
        type=int,
        default=20,
        help="iperf3 client duration in seconds.",
    )
    parser.add_argument(
        "--loopback-pair",
        nargs=2,
        metavar=("IFACE_A", "IFACE_B"),
        action="append",
        default=[],
        help="Pair of interfaces connected by a loopback cable.",
    )
    parser.add_argument(
        "--external-interface",
        action="append",
        default=[],
        help="Interface that should be linked to the external network.",
    )
    parser.add_argument(
        "--auto-network",
        dest="auto_network",
        action="store_true",
        default=True,
        help="Automatically inventory physical network interfaces during preflight.",
    )
    parser.add_argument(
        "--no-auto-network",
        dest="auto_network",
        action="store_false",
        help="Disable automatic network inventory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"{sanitize_label(args.label)}_quick_{timestamp}"
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    requested_tools = collect_required_tools(args)
    os_support = detect_os_support()
    preflight = run_preflight(args, logs_dir, requested_tools, os_support)
    install_result = None
    if args.install_missing and preflight["missing_tools"]:
        if args.yes or confirm_install(preflight["missing_tools"], os_support):
            install_result = install_missing_tools(preflight["missing_tools"], logs_dir, os_support)
            preflight = run_preflight(args, logs_dir, requested_tools, os_support)
        else:
            install_result = {
                "status": "SKIP",
                "message": "Package installation was not confirmed by the operator.",
            }

    results: dict[str, Any] = {
        "label": args.label,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "hostname": run_command_text("hostname").strip() or "unknown",
        "requested_checks": describe_requested_checks(args),
        "preflight": preflight,
        "install_result": install_result,
        "tests": [],
    }

    if not args.preflight_only:
        if args.memory_seconds > 0:
            results["tests"].append(run_memory_test(args.memory_seconds, logs_dir))

        if args.storage_dir:
            results["tests"].append(
                run_storage_test(Path(args.storage_dir), args.storage_mb, logs_dir)
            )

        if args.network_server:
            results["tests"].append(
                run_network_test(args.network_server, args.network_seconds, logs_dir)
            )

        for index, pair in enumerate(args.loopback_pair):
            results["tests"].append(
                run_loopback_pair_test(pair[0], pair[1], index, args.network_seconds, logs_dir)
            )
    else:
        results["tests"].append(
            {
                "name": "active_checks",
                "status": "SKIP",
                "message": "Preflight-only mode. No active checks were executed.",
            }
        )

    if not args.preflight_only and not results["tests"]:
        results["tests"].append(
            {
                "name": "no_active_test_selected",
                "status": "SKIP",
                "message": "No active check was requested. Use memory, storage, network, or loopback arguments.",
            }
        )

    results["finished_at"] = datetime.now().isoformat(timespec="seconds")
    results["test_status"] = overall_status(results["tests"])
    results["overall_status"] = combine_statuses(
        preflight["overall_status"],
        results["test_status"],
    )

    output_path = run_dir / "quick_check.json"
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Quick check saved to {output_path}")
    return 0


def collect_required_tools(args: argparse.Namespace) -> dict[str, str]:
    tools: dict[str, str] = {}
    if args.memory_seconds > 0:
        tools["stress-ng"] = "sudo apt install -y stress-ng"
    if args.network_server or args.loopback_pair:
        tools["iperf3"] = "sudo apt install -y iperf3"
    if args.loopback_pair:
        tools["ip"] = "iproute2 is required; install your distro package if missing"
    if args.loopback_pair or args.external_interface:
        tools["ethtool"] = "sudo apt install -y ethtool"
    return tools


def describe_requested_checks(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "memory_seconds": args.memory_seconds,
        "storage_dir": args.storage_dir,
        "storage_mb": args.storage_mb if args.storage_dir else 0,
        "network_server": args.network_server,
        "network_seconds": args.network_seconds,
        "loopback_pairs": args.loopback_pair,
        "external_interfaces": args.external_interface,
        "auto_network": args.auto_network,
        "preflight_only": args.preflight_only,
        "install_missing": args.install_missing,
        "yes": args.yes,
    }


def run_preflight(
    args: argparse.Namespace,
    logs_dir: Path,
    requested_tools: dict[str, str],
    os_support: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    missing_tools: list[dict[str, str]] = []

    for tool_name, install_hint in requested_tools.items():
        present = shutil.which(tool_name) is not None
        check = {
            "name": f"tool_{tool_name}",
            "status": "PASS" if present else "BLOCKED",
            "message": "tool available" if present else "tool missing",
            "tool": tool_name,
            "install_hint": install_hint,
        }
        checks.append(check)
        if not present:
            missing_tools.append({"tool": tool_name, "install_hint": install_hint})

    if args.auto_network:
        checks.append(discover_network_inventory(logs_dir))

    for iface in args.external_interface:
        checks.append(
            check_interface_readiness(
                iface,
                role="external_network",
                logs_dir=logs_dir,
                required_link=True,
                expected_speed_gbps=None,
                cable_hint="Check external LAN cable, switch port, and negotiated speed.",
            )
        )

    for iface_a, iface_b in args.loopback_pair:
        checks.append(
            check_interface_readiness(
                iface_a,
                role=f"loopback_pair:{iface_b}",
                logs_dir=logs_dir,
                required_link=True,
                expected_speed_gbps=10,
                cable_hint=f"Check the loopback cable between {iface_a} and {iface_b}.",
            )
        )
        checks.append(
            check_interface_readiness(
                iface_b,
                role=f"loopback_pair:{iface_a}",
                logs_dir=logs_dir,
                required_link=True,
                expected_speed_gbps=10,
                cable_hint=f"Check the loopback cable between {iface_a} and {iface_b}.",
            )
        )

    usb_hints = detect_usb_cable_hints(logs_dir)
    for hint in usb_hints:
        checks.append(
            {
                "name": "usb_cable_hint",
                "status": "BLOCKED",
                "message": hint,
            }
        )

    notes = []
    if missing_tools:
        notes.append("Missing tools were detected. Install them or skip the related active checks.")
    if missing_tools and not os_support.get("install_supported"):
        notes.append(os_support.get("install_message", "Automatic install is not supported on this OS."))
    if args.auto_network:
        notes.append("Network inventory was auto-discovered from the DUT. Configure explicit pairs only for cabled active checks.")
    if args.loopback_pair:
        notes.append("Loopback iperf test will temporarily add and remove IPv4 addresses on the loopback pair when active checks are enabled.")

    return {
        "overall_status": overall_status(checks),
        "os_support": os_support,
        "missing_tools": missing_tools,
        "checks": checks,
        "notes": notes,
    }


def detect_os_support() -> dict[str, Any]:
    os_release = parse_os_release(Path("/etc/os-release"))
    os_id = os_release.get("ID", "").lower()
    id_like = {
        item.lower()
        for item in os_release.get("ID_LIKE", "").replace(",", " ").split()
        if item.strip()
    }
    apt_available = shutil.which("apt-get") is not None
    apt_family = os_id in {"ubuntu", "debian"} or bool(id_like & {"ubuntu", "debian"})
    install_supported = apt_available and apt_family

    if install_supported:
        install_message = (
            "Automatic install is supported through apt-get. "
            "The DUT still needs network or mirror access and sudo/root permission."
        )
    elif apt_available:
        install_message = (
            "apt-get exists, but this OS is not identified as Ubuntu/Debian family. "
            "Install missing tools manually or validate the package manager first."
        )
    else:
        install_message = (
            "Automatic install is currently supported only on Ubuntu/Debian-like DUTs "
            "with apt-get available."
        )

    return {
        "pretty_name": os_release.get("PRETTY_NAME", "Unknown Linux"),
        "id": os_id or "unknown",
        "id_like": sorted(id_like),
        "package_manager": "apt-get" if apt_available else "",
        "install_supported": install_supported,
        "install_message": install_message,
    }


def parse_os_release(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value.strip().strip('"')
    return result


def confirm_install(missing_tools: list[dict[str, str]], os_support: dict[str, Any]) -> bool:
    tools = ", ".join(item["tool"] for item in missing_tools)
    print()
    print("Missing tools detected: " + tools)
    print(os_support.get("install_message", "Automatic install may not be supported."))
    print("Installing packages changes the DUT and requires network or mirror access.")
    print("It may also require root or passwordless sudo permission.")
    try:
        answer = input("Install missing packages now? Type Y to continue: ").strip()
    except EOFError:
        return False
    return answer.upper() == "Y"


def package_manager_command(args: list[str]) -> list[str]:
    command = ["apt-get", *args]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return command
    if shutil.which("sudo"):
        return ["sudo", "-n", *command]
    return command


def install_missing_tools(
    missing_tools: list[dict[str, str]],
    logs_dir: Path,
    os_support: dict[str, Any],
) -> dict[str, Any]:
    log_path = logs_dir / "install_missing.log"
    if not os_support.get("install_supported"):
        message = os_support.get("install_message", "Automatic install is not supported on this OS.")
        log_path.write_text(message + "\n", encoding="utf-8")
        return {
            "status": "SKIP",
            "message": message,
            "os_support": os_support,
            "log_file": str(log_path),
        }

    tools = sorted(
        {
            item["tool"]
            for item in missing_tools
            if item["tool"] in {"stress-ng", "iperf3", "ethtool"}
        }
    )
    if not tools:
        log_path.write_text("No supported apt packages need installation.\n", encoding="utf-8")
        return {
            "status": "SKIP",
            "message": "No supported apt packages need installation.",
            "log_file": str(log_path),
        }

    steps: list[dict[str, Any]] = []
    update_cmd = package_manager_command(["update"])
    update_result = subprocess.run(update_cmd, capture_output=True, text=True)
    steps.append(
        {
            "command": update_cmd,
            "returncode": update_result.returncode,
            "stdout": update_result.stdout,
            "stderr": update_result.stderr,
        }
    )
    if update_result.returncode != 0:
        log_path.write_text(format_install_log(steps), encoding="utf-8")
        return {
            "status": "FAIL",
            "message": "apt-get update failed. Check DUT network, proxy, and sudo/root permission.",
            "log_file": str(log_path),
        }

    install_cmd = package_manager_command(["install", "-y", *tools])
    install_result = subprocess.run(install_cmd, capture_output=True, text=True)
    steps.append(
        {
            "command": install_cmd,
            "returncode": install_result.returncode,
            "stdout": install_result.stdout,
            "stderr": install_result.stderr,
        }
    )
    log_path.write_text(format_install_log(steps), encoding="utf-8")
    return {
        "status": "PASS" if install_result.returncode == 0 else "FAIL",
        "message": "Installed missing packages" if install_result.returncode == 0 else "apt-get install failed. Check DUT network, proxy, and sudo/root permission.",
        "packages": tools,
        "log_file": str(log_path),
    }


def discover_network_inventory(logs_dir: Path) -> dict[str, Any]:
    log_path = logs_dir / "preflight_network_inventory.json"
    interfaces = []
    default_interfaces = detect_default_route_interfaces()
    base = Path("/sys/class/net")

    if base.exists():
        for iface_path in sorted(base.iterdir(), key=lambda item: item.name):
            iface = iface_path.name
            if iface == "lo":
                continue
            interface_type = "physical" if (iface_path / "device").exists() else "virtual"
            carrier_text = read_file_text(iface_path / "carrier").strip()
            speed_text = read_file_text(iface_path / "speed").strip()
            speed_mbps = int(speed_text) if speed_text.isdigit() and int(speed_text) >= 0 else None
            addresses = list_ipv4_addresses(iface)
            interfaces.append(
                {
                    "interface": iface,
                    "type": interface_type,
                    "operstate": read_file_text(iface_path / "operstate").strip() or "unknown",
                    "carrier": carrier_text,
                    "link_detected": carrier_text == "1",
                    "speed_mbps": speed_mbps,
                    "mac": read_file_text(iface_path / "address").strip(),
                    "driver": resolve_driver_name(iface_path),
                    "ipv4_addresses": addresses,
                    "is_default_route": iface in default_interfaces,
                }
            )

    physical = [item for item in interfaces if item["type"] == "physical"]
    active = [item for item in physical if item["link_detected"] or item["ipv4_addresses"]]
    log_path.write_text(
        json.dumps(
            {
                "default_route_interfaces": default_interfaces,
                "interfaces": interfaces,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    if not physical:
        return {
            "name": "network_inventory",
            "status": "BLOCKED",
            "message": "No physical network interface was discovered.",
            "interfaces": interfaces,
            "log_file": str(log_path),
        }

    default_text = ", ".join(default_interfaces) if default_interfaces else "none"
    return {
        "name": "network_inventory",
        "status": "PASS",
        "message": (
            f"Discovered {len(physical)} physical interface(s); "
            f"{len(active)} currently linked or addressed; default route interface(s): {default_text}."
        ),
        "interfaces": interfaces,
        "default_route_interfaces": default_interfaces,
        "log_file": str(log_path),
    }


def detect_default_route_interfaces() -> list[str]:
    output = run_command_text("ip route show default")
    interfaces = []
    for line in output.splitlines():
        match = re.search(r"\bdev\s+(\S+)", line)
        if match:
            interfaces.append(match.group(1))
    return sorted(set(interfaces))


def resolve_driver_name(iface_path: Path) -> str:
    driver_path = iface_path / "device" / "driver"
    try:
        if driver_path.exists():
            return driver_path.resolve().name
    except OSError:
        return ""
    return ""


def check_interface_readiness(
    iface: str,
    role: str,
    logs_dir: Path,
    required_link: bool,
    expected_speed_gbps: int | None,
    cable_hint: str,
) -> dict[str, Any]:
    log_path = logs_dir / f"preflight_{sanitize_label(iface)}.log"
    present = Path("/sys/class/net", iface).exists()
    if not present:
        log_path.write_text(f"interface not found: {iface}\n", encoding="utf-8")
        return {
            "name": f"interface_{iface}",
            "status": "BLOCKED",
            "role": role,
            "interface": iface,
            "message": f"Interface {iface} not found",
            "cable_hint": cable_hint,
            "log_file": str(log_path),
        }

    speed_text = read_file_text(Path("/sys/class/net", iface, "speed")).strip()
    carrier_text = read_file_text(Path("/sys/class/net", iface, "carrier")).strip()
    ipv4_addresses = list_ipv4_addresses(iface)
    ethtool_output = run_simple_command(["ethtool", iface]) if shutil.which("ethtool") else ""
    log_lines = [
        f"interface: {iface}",
        f"role: {role}",
        f"sysfs_speed: {speed_text or 'unknown'}",
        f"sysfs_carrier: {carrier_text or 'unknown'}",
        f"ipv4_addresses: {', '.join(ipv4_addresses) if ipv4_addresses else 'none'}",
        "",
        "[ethtool]",
        ethtool_output.rstrip(),
    ]
    log_path.write_text("\n".join(log_lines).rstrip() + "\n", encoding="utf-8")

    link_detected = parse_link_detected(ethtool_output)
    if link_detected is None:
        link_detected = carrier_text == "1"
    speed_mbps = parse_speed_mbps(ethtool_output)
    if speed_mbps is None and speed_text.isdigit():
        speed_mbps = int(speed_text)

    messages = []
    status = "PASS"
    if required_link and not link_detected:
        status = "BLOCKED"
        messages.append("Link is down")
        messages.append(cable_hint)
    if expected_speed_gbps is not None and speed_mbps is not None:
        if speed_mbps < expected_speed_gbps * 1000:
            status = "BLOCKED"
            messages.append(
                f"Negotiated speed is {speed_mbps} Mb/s, lower than expected {expected_speed_gbps} Gb/s"
            )
    if not messages:
        messages.append("Interface is ready for the requested check")

    return {
        "name": f"interface_{iface}",
        "status": status,
        "role": role,
        "interface": iface,
        "link_detected": link_detected,
        "speed_mbps": speed_mbps,
        "ipv4_addresses": ipv4_addresses,
        "message": "; ".join(messages),
        "log_file": str(log_path),
    }


def detect_usb_cable_hints(logs_dir: Path) -> list[str]:
    command = ["dmesg", "-T"]
    completed = subprocess.run(command, capture_output=True, text=True)
    log_path = logs_dir / "preflight_dmesg_usb.log"
    log_path.write_text(format_process_log(command, completed), encoding="utf-8")
    if completed.returncode != 0:
        return []

    hints = []
    patterns = [
        r"Maybe the USB cable is bad",
        r"unable to enumerate USB device",
        r"device descriptor read/64",
    ]
    for line in completed.stdout.splitlines()[-300:]:
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                hints.append(line.strip())
                break
    counts = Counter()
    if any("Maybe the USB cable is bad" in line for line in hints):
        counts["USB port reported 'Maybe the USB cable is bad'"] = sum(
            1 for line in hints if "Maybe the USB cable is bad" in line
        )
    if any("unable to enumerate USB device" in line for line in hints):
        counts["USB device enumeration failed"] = sum(
            1 for line in hints if "unable to enumerate USB device" in line
        )
    if any("device descriptor read/64" in line for line in hints):
        counts["USB device descriptor read failed"] = sum(
            1 for line in hints if "device descriptor read/64" in line
        )
    return [f"{message} ({count}x)" for message, count in counts.items()]


def run_memory_test(seconds: int, logs_dir: Path) -> dict[str, Any]:
    log_path = logs_dir / "memory_stress.log"
    if shutil.which("stress-ng") is None:
        log_path.write_text("stress-ng not found\n", encoding="utf-8")
        return {
            "name": "memory_stress",
            "status": "SKIP",
            "seconds": seconds,
            "message": "stress-ng not found",
            "install_hint": "sudo apt install -y stress-ng",
            "log_file": str(log_path),
        }

    command = [
        "stress-ng",
        "--vm",
        "2",
        "--vm-bytes",
        "70%",
        "--timeout",
        f"{seconds}s",
        "--metrics-brief",
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    log_path.write_text(format_process_log(command, completed), encoding="utf-8")
    return {
        "name": "memory_stress",
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "seconds": seconds,
        "returncode": completed.returncode,
        "log_file": str(log_path),
    }


def run_storage_test(storage_dir: Path, storage_mb: int, logs_dir: Path) -> dict[str, Any]:
    log_path = logs_dir / "storage_smoke.log"
    start = time.perf_counter()

    if not storage_dir.exists():
        log_path.write_text(f"storage dir does not exist: {storage_dir}\n", encoding="utf-8")
        return {
            "name": "storage_file_smoke",
            "status": "FAIL",
            "message": f"storage dir does not exist: {storage_dir}",
            "log_file": str(log_path),
        }

    fd, temp_name = tempfile.mkstemp(prefix="dqa_storage_", suffix=".bin", dir=storage_dir)
    os.close(fd)
    temp_path = Path(temp_name)

    try:
        block = random.randbytes(1024 * 1024)
        hasher = hashlib.sha256()
        with temp_path.open("wb") as handle:
            for _ in range(storage_mb):
                handle.write(block)
                hasher.update(block)
            handle.flush()
            os.fsync(handle.fileno())
        write_seconds = time.perf_counter() - start

        read_start = time.perf_counter()
        verify = hashlib.sha256()
        with temp_path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                verify.update(chunk)
        read_seconds = time.perf_counter() - read_start

        expected = hasher.hexdigest()
        actual = verify.hexdigest()
        status = "PASS" if expected == actual else "FAIL"
        log_lines = [
            f"file: {temp_path}",
            f"size_mb: {storage_mb}",
            f"write_seconds: {write_seconds:.3f}",
            f"read_seconds: {read_seconds:.3f}",
            f"expected_sha256: {expected}",
            f"actual_sha256: {actual}",
            f"status: {status}",
        ]
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return {
            "name": "storage_file_smoke",
            "status": status,
            "storage_dir": str(storage_dir),
            "storage_mb": storage_mb,
            "write_seconds": round(write_seconds, 3),
            "read_seconds": round(read_seconds, 3),
            "log_file": str(log_path),
        }
    finally:
        temp_path.unlink(missing_ok=True)


def run_network_test(server: str, seconds: int, logs_dir: Path) -> dict[str, Any]:
    log_path = logs_dir / "network_iperf3.log"
    if shutil.which("iperf3") is None:
        log_path.write_text("iperf3 not found\n", encoding="utf-8")
        return {
            "name": "network_iperf3",
            "status": "SKIP",
            "message": "iperf3 not found",
            "install_hint": "sudo apt install -y iperf3",
            "log_file": str(log_path),
        }

    command = ["iperf3", "-c", server, "-t", str(seconds), "--json"]
    completed = subprocess.run(command, capture_output=True, text=True)
    log_path.write_text(format_process_log(command, completed), encoding="utf-8")

    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(completed.stdout) if completed.stdout else {}
    except json.JSONDecodeError:
        parsed = {}

    bits_per_second = (
        parsed.get("end", {})
        .get("sum_received", {})
        .get("bits_per_second")
    ) or (
        parsed.get("end", {})
        .get("sum_sent", {})
        .get("bits_per_second")
    )
    return {
        "name": "network_iperf3",
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "server": server,
        "seconds": seconds,
        "returncode": completed.returncode,
        "bits_per_second": bits_per_second,
        "log_file": str(log_path),
    }


def run_loopback_pair_test(
    iface_a: str,
    iface_b: str,
    pair_index: int,
    seconds: int,
    logs_dir: Path,
) -> dict[str, Any]:
    log_path = logs_dir / f"loopback_{sanitize_label(iface_a)}_{sanitize_label(iface_b)}.log"
    if shutil.which("iperf3") is None:
        log_path.write_text("iperf3 not found\n", encoding="utf-8")
        return {
            "name": f"loopback_iperf3_{iface_a}_{iface_b}",
            "status": "SKIP",
            "message": "iperf3 not found",
            "install_hint": "sudo apt install -y iperf3",
            "log_file": str(log_path),
        }
    if shutil.which("ip") is None:
        log_path.write_text("ip command not found\n", encoding="utf-8")
        return {
            "name": f"loopback_iperf3_{iface_a}_{iface_b}",
            "status": "SKIP",
            "message": "ip command not found",
            "install_hint": "Install the iproute2 package for your distro",
            "log_file": str(log_path),
        }

    existing_a = list_ipv4_addresses(iface_a)
    existing_b = list_ipv4_addresses(iface_b)
    if existing_a or existing_b:
        log_lines = [
            f"{iface_a} existing IPv4: {', '.join(existing_a) if existing_a else 'none'}",
            f"{iface_b} existing IPv4: {', '.join(existing_b) if existing_b else 'none'}",
            "Refusing to modify interface addresses because one of the interfaces is already in use.",
        ]
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return {
            "name": f"loopback_iperf3_{iface_a}_{iface_b}",
            "status": "SKIP",
            "message": "Existing IPv4 address detected. Skipped temporary loopback reconfiguration.",
            "log_file": str(log_path),
        }

    octet = 10 + pair_index
    server_ip = f"198.18.{octet}.1"
    client_ip = f"198.18.{octet}.2"
    prefix = "30"

    server_process = None
    log_chunks = []
    try:
        log_chunks.append(capture_command(["ip", "link", "set", iface_a, "up"]))
        log_chunks.append(capture_command(["ip", "link", "set", iface_b, "up"]))
        log_chunks.append(
            capture_command(["ip", "addr", "add", f"{server_ip}/{prefix}", "dev", iface_a])
        )
        log_chunks.append(
            capture_command(["ip", "addr", "add", f"{client_ip}/{prefix}", "dev", iface_b])
        )
        time.sleep(1.0)

        server_command = ["iperf3", "-s", "-1", "-B", server_ip, "--json"]
        server_process = subprocess.Popen(
            server_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(2.0)

        client_command = [
            "iperf3",
            "-c",
            server_ip,
            "-B",
            client_ip,
            "-t",
            str(seconds),
            "--json",
        ]
        client_result = subprocess.run(client_command, capture_output=True, text=True)
        server_stdout, server_stderr = server_process.communicate(timeout=20)

        log_chunks.append(
            format_process_log(
                server_command,
                subprocess.CompletedProcess(
                    server_command,
                    server_process.returncode or 0,
                    server_stdout,
                    server_stderr,
                ),
            )
        )
        log_chunks.append(format_process_log(client_command, client_result))
        log_path.write_text("\n\n".join(log_chunks).rstrip() + "\n", encoding="utf-8")

        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(client_result.stdout) if client_result.stdout else {}
        except json.JSONDecodeError:
            parsed = {}
        bits_per_second = (
            parsed.get("end", {}).get("sum_received", {}).get("bits_per_second")
        ) or (
            parsed.get("end", {}).get("sum_sent", {}).get("bits_per_second")
        )
        return {
            "name": f"loopback_iperf3_{iface_a}_{iface_b}",
            "status": "PASS" if client_result.returncode == 0 else "FAIL",
            "interface_a": iface_a,
            "interface_b": iface_b,
            "server_ip": server_ip,
            "client_ip": client_ip,
            "seconds": seconds,
            "bits_per_second": bits_per_second,
            "log_file": str(log_path),
        }
    except subprocess.TimeoutExpired:
        log_chunks.append("iperf3 server timeout")
        log_path.write_text("\n\n".join(log_chunks).rstrip() + "\n", encoding="utf-8")
        return {
            "name": f"loopback_iperf3_{iface_a}_{iface_b}",
            "status": "FAIL",
            "message": "iperf3 server timeout",
            "log_file": str(log_path),
        }
    finally:
        if server_process is not None and server_process.poll() is None:
            server_process.kill()
            server_process.wait(timeout=5)
        capture_command(["ip", "addr", "del", f"{server_ip}/{prefix}", "dev", iface_a], check=False)
        capture_command(["ip", "addr", "del", f"{client_ip}/{prefix}", "dev", iface_b], check=False)


def combine_statuses(*statuses: str) -> str:
    present = {status for status in statuses if status}
    if "FAIL" in present:
        return "FAIL"
    if "BLOCKED" in present:
        return "BLOCKED"
    if "PASS" in present:
        return "PASS"
    return "SKIP"


def overall_status(tests: list[dict[str, Any]]) -> str:
    statuses = {item.get("status", "SKIP") for item in tests}
    return combine_statuses(*statuses)


def format_process_log(command: list[str], completed: subprocess.CompletedProcess[str]) -> str:
    lines = [
        "$ " + " ".join(command),
        f"[returncode] {completed.returncode}",
        "",
        "[stdout]",
        (completed.stdout or "").rstrip(),
        "",
        "[stderr]",
        (completed.stderr or "").rstrip(),
        "",
    ]
    return "\n".join(lines)


def format_install_log(steps: list[dict[str, Any]]) -> str:
    chunks = []
    for step in steps:
        completed = subprocess.CompletedProcess(
            step["command"],
            step["returncode"],
            step["stdout"],
            step["stderr"],
        )
        chunks.append(format_process_log(step["command"], completed))
    return "\n\n".join(chunks).rstrip() + "\n"


def capture_command(command: list[str], check: bool = True) -> str:
    completed = subprocess.run(command, capture_output=True, text=True)
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return format_process_log(command, completed)


def run_simple_command(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True)
    return format_process_log(command, completed)


def run_command_text(command: str) -> str:
    completed = subprocess.run(command, shell=True, capture_output=True, text=True)
    return completed.stdout or ""


def read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def list_ipv4_addresses(iface: str) -> list[str]:
    completed = subprocess.run(
        ["ip", "-4", "-o", "addr", "show", "dev", iface],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return []
    addresses = []
    for line in completed.stdout.splitlines():
        match = re.search(r"\binet ([0-9.]+/[0-9]+)", line)
        if match:
            addresses.append(match.group(1))
    return addresses


def parse_link_detected(text: str) -> bool | None:
    match = re.search(r"Link detected:\s*(yes|no)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "yes"


def parse_speed_mbps(text: str) -> int | None:
    match = re.search(r"Speed:\s*([0-9]+)Mb/s", text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def sanitize_label(label: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in label.strip())
    return cleaned or "dut"


if __name__ == "__main__":
    raise SystemExit(main())
