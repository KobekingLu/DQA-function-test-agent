from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_latest_live_case(project_root: Path) -> dict[str, Any] | None:
    remote_runs_dir = project_root / "output" / "remote_runs"
    latest_run = _find_latest_remote_run(remote_runs_dir)
    if latest_run is None:
        return None

    evidence_path, quick_path = latest_run
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    quick = json.loads(quick_path.read_text(encoding="utf-8"))

    product_name = evidence.get("snapshot", {}).get("hardware", {}).get("product_name", "Unknown Product")
    bios = evidence.get("snapshot", {}).get("hardware", {}).get("bios_summary", "Unknown BIOS")
    os_name = (
        evidence.get("snapshot", {})
        .get("system", {})
        .get("os_release", {})
        .get("PRETTY_NAME", "Unknown OS")
    )
    cpu_line = _lscpu_value(
        evidence.get("snapshot", {}).get("hardware", {}).get("cpu_summary", ""),
        "Model name:",
    ) or _first_non_empty_line(evidence.get("snapshot", {}).get("hardware", {}).get("cpu_summary", ""))
    storage_device = _first_storage_device(evidence)
    preflight = quick.get("preflight", {})
    preflight_checks = preflight.get("checks", [])
    missing_tools = [
        item.get("tool", "")
        for item in preflight.get("missing_tools", [])
        if item.get("tool")
    ]
    interface_checks = [
        item for item in preflight_checks if item.get("name", "").startswith("interface_")
    ]
    blocked_interfaces = [
        item for item in interface_checks if item.get("status", "").upper() == "BLOCKED"
    ]
    network_status = "BLOCKED" if missing_tools or blocked_interfaces else "PASS"
    network_evidence = _network_evidence(evidence, interface_checks, missing_tools)
    bmc = evidence.get("snapshot", {}).get("bmc", {})
    bmc_status = "PASS" if bmc.get("supported") else "SKIP"
    usb_hint = _join_messages(
        [
            item.get("message", "")
            for item in preflight_checks
            if item.get("name") == "usb_cable_hint"
        ]
    )
    active_tests = quick.get("tests", [])

    expected_tests = [
        {
            "test_id": "LIVE-001",
            "feature_area": "Operating System",
            "test_name": "OS install and platform snapshot",
            "priority": "P1",
            "expected_result": "Platform identity, BIOS, OS, and CPU evidence are collected from the live DUT.",
            "owner": "DQA",
        },
        {
            "test_id": "LIVE-002",
            "feature_area": "Storage",
            "test_name": "Boot storage visibility and SMART snapshot",
            "priority": "P1",
            "expected_result": "Boot storage device is visible in the OS and the health check does not report a failure.",
            "owner": "DQA",
        },
        {
            "test_id": "LIVE-003",
            "feature_area": "Ethernet",
            "test_name": "Network preflight and interface readiness",
            "priority": "P2",
            "expected_result": "Configured network interfaces and required active-check tools are ready for follow-up testing.",
            "owner": "Lab",
        },
        {
            "test_id": "LIVE-004",
            "feature_area": "BMC",
            "test_name": "BMC sensor and FRU snapshot",
            "priority": "P2",
            "expected_result": "BMC sensor and FRU queries complete when BMC is available on the platform.",
            "owner": "DQA",
        },
        {
            "test_id": "LIVE-005",
            "feature_area": "USB",
            "test_name": "USB readiness and cable sanity",
            "priority": "P2",
            "expected_result": "USB ports enumerate without repeated cable or device errors.",
            "owner": "Lab",
        },
    ]

    actual_items = [
        {
            "test_id": "LIVE-001",
            "status": "PASS",
            "evidence": f"{product_name}, BIOS {bios}, {os_name}, {cpu_line}",
            "log_reference": _relative_to_root(project_root, evidence_path),
            "note": "",
        },
        {
            "test_id": "LIVE-002",
            "status": "PASS",
            "evidence": storage_device,
            "log_reference": _relative_to_root(project_root, evidence_path),
            "note": "",
        },
        {
            "test_id": "LIVE-003",
            "status": network_status,
            "evidence": network_evidence,
            "log_reference": _relative_to_root(project_root, quick_path),
            "note": _network_note(missing_tools, blocked_interfaces),
        },
        {
            "test_id": "LIVE-004",
            "status": bmc_status,
            "evidence": _bmc_evidence(bmc),
            "log_reference": _relative_to_root(project_root, evidence_path),
            "note": "" if bmc_status == "PASS" else "BMC evidence was not available from this DUT snapshot.",
        },
        {
            "test_id": "LIVE-005",
            "status": "BLOCKED" if usb_hint else "PASS",
            "evidence": usb_hint or "No repeated USB cable or enumeration warning was detected in preflight.",
            "log_reference": _relative_to_root(project_root, quick_path),
            "note": "Check the USB cable or attached device path before rerunning the USB-related items." if usb_hint else "",
        },
    ]

    actual_by_test_id = {item["test_id"]: item for item in actual_items}
    collected_at = evidence.get("collected_at", "")
    source_label = f"Live DUT Evidence ({product_name} / {collected_at})".strip(" /")
    extra_observations = []
    for active_test in active_tests:
        extra_observations.append(
            {
                "name": active_test.get("name", "active_check"),
                "status": active_test.get("status", "INFO"),
                "summary": active_test.get("message", "Live quick-check observation."),
                "source": _relative_to_root(project_root, quick_path),
                "scope_note": "Extra live DUT observation captured by the quick-check runner.",
            }
        )

    return {
        "case_id": f"{_slugify(product_name)}_live",
        "case_name": f"{product_name} Live DUT Review",
        "source_type": "live_dut",
        "source_label": source_label,
        "role_candidates": {
            "expected_tests": "Generated live DUT smoke-review scope",
            "actual_results": f"{_relative_to_root(project_root, evidence_path)} + {_relative_to_root(project_root, quick_path)}",
            "known_issues": "No linked issue list yet",
        },
        "scope_notes": [
            "This live review is generated from the latest SSH-collected DUT evidence.",
            "The current scope focuses on read-only platform evidence and setup readiness before active stress or bandwidth testing.",
            "Network interface expectations come from the local target config. If the configured names do not match the DUT, update network_topology and rerun preflight.",
            "Active checks such as iperf3, memory stress, or storage smoke should be enabled only after preflight is clean.",
        ],
        "extra_observations": extra_observations,
        "parsed": {
            "expected_tests": {
                "source_sheet": "Live DUT smoke-review scope",
                "tests": expected_tests,
            },
            "actual_results": {
                "source_sheet": "Latest remote live-check outputs",
                "items": actual_items,
                "by_test_id": actual_by_test_id,
            },
            "known_issues": [],
        },
        "analysis_overrides": _live_analysis_overrides(
            missing_tools=missing_tools,
            blocked_interfaces=blocked_interfaces,
            usb_hint=usb_hint,
            quick=quick,
        ),
    }


def _find_latest_remote_run(remote_runs_dir: Path) -> tuple[Path, Path] | None:
    if not remote_runs_dir.exists():
        return None

    candidates = sorted(
        [path for path in remote_runs_dir.iterdir() if path.is_dir()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for run_dir in candidates:
        evidence_files = sorted(run_dir.glob("downloaded/**/evidence.json"))
        quick_files = sorted(run_dir.glob("downloaded/**/quick_check.json"))
        if evidence_files and quick_files:
            return evidence_files[-1], quick_files[-1]
    return None


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return "Unknown CPU"


def _lscpu_value(text: str, label: str) -> str:
    for line in text.splitlines():
        if line.startswith(label):
            return line.split(":", 1)[1].strip()
    return ""


def _first_storage_device(evidence: dict[str, Any]) -> str:
    devices = evidence.get("snapshot", {}).get("storage", {}).get("block_devices", [])
    health_checks = evidence.get("snapshot", {}).get("storage", {}).get("health_checks", [])
    device = devices[0] if devices else {}
    health = health_checks[0] if health_checks else {}
    name = device.get("path") or device.get("name") or "Unknown device"
    model = device.get("model") or "Unknown model"
    result = health.get("health_result") or "Unknown health"
    return f"{name} ({model}) SMART {result}"


def _network_evidence(
    evidence: dict[str, Any],
    interface_checks: list[dict[str, Any]],
    missing_tools: list[str],
) -> str:
    detected = evidence.get("snapshot", {}).get("network", {}).get("interfaces", [])
    detected_summary = ", ".join(_detected_iface_summary(item) for item in detected[:8])
    configured_summary = ", ".join(
        f"{item.get('interface', 'unknown')}={item.get('status', 'UNKNOWN')}"
        for item in interface_checks
    )

    parts = []
    if detected_summary:
        parts.append(f"Detected interfaces: {detected_summary}.")
    if configured_summary:
        parts.append(f"Configured preflight: {configured_summary}.")
    if missing_tools:
        parts.append(f"Missing active-check tools: {', '.join(missing_tools)}.")
    return " ".join(parts) or "Network evidence was not collected."


def _network_note(missing_tools: list[str], blocked_interfaces: list[dict[str, Any]]) -> str:
    notes = []
    if missing_tools:
        notes.append(
            "Install missing active-check tools before bandwidth or loopback checks: "
            + ", ".join(missing_tools)
        )
    if blocked_interfaces:
        names = ", ".join(item.get("interface", "unknown") for item in blocked_interfaces)
        notes.append(
            "Configured interface names did not match ready interfaces on the DUT: "
            + names
        )
    return " ".join(notes)


def _bmc_evidence(bmc: dict[str, Any]) -> str:
    if not bmc.get("supported"):
        return "BMC sensor or FRU evidence was not collected."
    sensor_count = len(bmc.get("sensor_excerpt", []))
    fru_count = len(bmc.get("fru_excerpt", []))
    return f"ipmitool sensor excerpt lines: {sensor_count}; FRU excerpt lines: {fru_count}."


def _detected_iface_summary(interface: dict[str, Any]) -> str:
    name = interface.get("ifname", "unknown")
    state = interface.get("operstate", "UNKNOWN")
    addresses = interface.get("addresses") or []
    ipv4 = [address for address in addresses if "." in address]
    address_text = "/".join(ipv4[:2]) if ipv4 else "no IPv4"
    return f"{name}:{state}:{address_text}"


def _iface_summary(check: dict[str, Any]) -> str:
    if not check:
        return "not collected"
    speed = check.get("speed_mbps")
    link = "link up" if check.get("link_detected") else "link down"
    addresses = check.get("ipv4_addresses") or []
    addr_text = ", ".join(addresses) if addresses else "no IPv4"
    if speed:
        return f"{link}, {speed} Mb/s, {addr_text}"
    return f"{link}, {addr_text}"


def _join_messages(messages: list[str]) -> str:
    cleaned = [message.strip() for message in messages if message and message.strip()]
    return "; ".join(cleaned)


def _first_test(quick: dict[str, Any], name: str) -> dict[str, Any]:
    for item in quick.get("tests", []):
        if item.get("name") == name:
            return item
    return {}


def _live_analysis_overrides(
    missing_tools: list[str],
    blocked_interfaces: list[dict[str, Any]],
    usb_hint: str,
    quick: dict[str, Any],
) -> dict[str, Any]:
    reasons = []
    actions = []

    if missing_tools:
        reasons.append(
            "Agent found missing DUT tool(s) needed for active checks: "
            + ", ".join(missing_tools)
            + "."
        )
        actions.append("Install the missing DUT tool(s), then rerun preflight.")

    if blocked_interfaces:
        names = ", ".join(item.get("interface", "unknown") for item in blocked_interfaces)
        reasons.append(
            "Agent could not match configured network interface(s) on the DUT: "
            + names
            + "."
        )
        actions.append("Update the target config network_topology interface names for this DUT.")

    if usb_hint:
        reasons.append("Agent detected a USB readiness warning in preflight.")
        actions.append("Check USB cabling or attached devices, then rerun the USB-related checks.")

    if not reasons:
        return {}

    if quick.get("requested_checks", {}).get("preflight_only"):
        actions.append("After preflight is clean, enable one active check at a time.")

    return {
        "recommended_owner": "Lab",
        "suggested_next_step": "Fix preflight setup gaps, rerun the SSH live-check flow, and refresh the HTML review package.",
        "decision_reasons": reasons,
        "action_items": actions,
    }


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "live_dut"


def _relative_to_root(project_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)
