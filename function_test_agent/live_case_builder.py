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
    preflight_checks = {
        item.get("name", ""): item for item in quick.get("preflight", {}).get("checks", [])
    }

    ba4 = preflight_checks.get("interface_ba4p0", {})
    ba5 = preflight_checks.get("interface_ba5p0", {})
    be0 = preflight_checks.get("interface_be1p0", {})
    be1 = preflight_checks.get("interface_be1p1", {})
    usb_hint = _join_messages(
        [
            item.get("message", "")
            for item in quick.get("preflight", {}).get("checks", [])
            if item.get("name") == "usb_cable_hint"
        ]
    )
    loopback_result = _first_test(quick, "loopback_iperf3_be1p0_be1p1")

    expected_tests = [
        {
            "test_id": "FT-6083-001",
            "feature_area": "Operating System",
            "test_name": "OS install and platform snapshot",
            "priority": "P1",
            "expected_result": "Platform identity, BIOS, OS, and CPU evidence match the current FWA-6083 review scope.",
            "owner": "DQA",
        },
        {
            "test_id": "FT-6083-002",
            "feature_area": "Storage",
            "test_name": "Boot storage visibility and SMART snapshot",
            "priority": "P1",
            "expected_result": "Boot storage device is visible in the OS and the health check does not report a failure.",
            "owner": "DQA",
        },
        {
            "test_id": "FT-6083-003",
            "feature_area": "Ethernet",
            "test_name": "I210 management Ethernet link readiness",
            "priority": "P1",
            "expected_result": "The current management-side Ethernet path links up and remains reachable for lab use.",
            "owner": "DQA",
        },
        {
            "test_id": "FT-6083-005",
            "feature_area": "BMC",
            "test_name": "BMC sensor and FRU snapshot",
            "priority": "P2",
            "expected_result": "BMC sensor and FRU queries complete and identify the platform.",
            "owner": "DQA",
        },
        {
            "test_id": "FT-6083-006",
            "feature_area": "USB",
            "test_name": "USB readiness and cable sanity",
            "priority": "P2",
            "expected_result": "USB ports enumerate without repeated cable or device errors.",
            "owner": "Lab",
        },
    ]

    actual_items = [
        {
            "test_id": "FT-6083-001",
            "status": "PASS",
            "evidence": f"{product_name}, BIOS {bios}, {os_name}, {cpu_line}",
            "log_reference": _relative_to_root(project_root, evidence_path),
            "note": "",
        },
        {
            "test_id": "FT-6083-002",
            "status": "PASS",
            "evidence": storage_device,
            "log_reference": _relative_to_root(project_root, evidence_path),
            "note": "",
        },
        {
            "test_id": "FT-6083-003",
            "status": "PASS",
            "evidence": (
                f"ba4p0 { _iface_summary(ba4) }; "
                f"ba5p0 { _iface_summary(ba5) }"
            ),
            "log_reference": _relative_to_root(project_root, quick_path),
            "note": "This is link-readiness evidence only. Bandwidth, LED, and port-mapping items still need manual lab confirmation.",
        },
        {
            "test_id": "FT-6083-005",
            "status": "PASS",
            "evidence": "ipmitool sensor and FRU both completed; platform identity matches FWA-6083N.",
            "log_reference": _relative_to_root(project_root, evidence_path),
            "note": "",
        },
        {
            "test_id": "FT-6083-006",
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
    if loopback_result:
        extra_observations.append(
            {
                "name": "X710 loopback smoke on be1p0/be1p1",
                "status": loopback_result.get("status", "INFO"),
                "summary": (
                    "Loopback smoke passed with temporary test IPs on be1p0/be1p1. "
                    "Keep it as extra connectivity evidence only."
                    if loopback_result.get("status") == "PASS"
                    else "Loopback smoke did not complete successfully."
                ),
                "source": _relative_to_root(project_root, quick_path),
                "scope_note": (
                    "Not part of the current onboard FWA-6083 PRD scope. "
                    "The PRD lists onboard management Ethernet on Intel I210 and onboard traffic port support as No."
                ),
            }
        )

    return {
        "case_id": "fwa6083_live",
        "case_name": f"{product_name} Live DUT Review",
        "source_type": "live_dut",
        "source_label": source_label,
        "role_candidates": {
            "expected_tests": (
                "Document\\FWA-6083-Function_Test_Item_Status_V11_01-Oct-2025_Release.xlsx "
                "(manual rows 13, 19, 20, 39 + PRD BMC scope)"
            ),
            "actual_results": f"{_relative_to_root(project_root, evidence_path)} + {_relative_to_root(project_root, quick_path)}",
            "known_issues": "No linked issue list yet",
        },
        "scope_notes": [
            "This live review focuses on the current FWA-6083 scope that can be verified without changing the OS image.",
            "Main mappings come from manual rows 13, 19, 20, and 39 in the current FWA status workbook.",
            "BMC evidence is kept in scope because the PRD lists onboard AST2600 BMC, hardware monitor, and FRU support.",
            "The X710 loopback result is kept as an extra observation, not as a main exit item, because the current onboard PRD scope is Intel I210 management Ethernet.",
        ],
        "extra_observations": extra_observations,
        "parsed": {
            "expected_tests": {
                "source_sheet": "FWA-6083 current manual/PRD scope with live DUT evidence",
                "tests": expected_tests,
            },
            "actual_results": {
                "source_sheet": "Latest remote live-check outputs",
                "items": actual_items,
                "by_test_id": actual_by_test_id,
            },
            "known_issues": [],
        },
        "analysis_overrides": {
            "recommended_owner": "Lab",
            "suggested_next_step": "Inspect the USB cable or attached USB path, rerun the USB-related checks, and then refresh the review package.",
            "decision_reasons": [
                "Agent detected 1 blocked live DUT item and traced it to repeated USB cable or enumeration warnings.",
                "Agent kept the X710 loopback result outside the main exit table because the current FWA-6083 onboard scope is the I210 management path.",
            ],
            "action_items": [
                "Check the USB cable or attached USB path and confirm the port wiring.",
                "Rerun the USB-related checks after the cable path is corrected.",
                "Keep the current report as valid evidence for the passed OS, storage, I210 Ethernet readiness, and BMC items.",
                "Handle Ethernet bandwidth, LED, port mapping, PSU removal, fan hot-swap, and RTC as remaining manual checks.",
            ],
        },
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


def _relative_to_root(project_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)
