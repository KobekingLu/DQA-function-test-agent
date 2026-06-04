from __future__ import annotations

from copy import deepcopy
from typing import Any


BUILTIN_PACKS: dict[str, dict[str, Any]] = {
    "io.inventory": {
        "pack_id": "io.inventory",
        "name": "IO Inventory",
        "description": "Read-only platform inventory for CPU, memory, USB, and PCIe context.",
        "requires": ["lscpu", "free", "lsusb", "lspci"],
        "test_cases": [
            {
                "test_id": "IO-CPU-001",
                "title": "CPU inventory is collectible",
                "feature_area": "CPU",
                "priority": "P2",
                "owner": "DQA",
                "intent": "Collect CPU topology and model information.",
                "steps": [{"type": "collect", "command": "lscpu"}],
                "evidence_requirements": ["cpu_summary"],
                "legacy_ids": ["cpu_info"]
            },
            {
                "test_id": "IO-MEM-001",
                "title": "Memory inventory is collectible",
                "feature_area": "Memory",
                "priority": "P2",
                "owner": "DQA",
                "intent": "Collect memory capacity and availability summary.",
                "steps": [{"type": "collect", "command": "free -m"}],
                "evidence_requirements": ["memory_summary"],
                "legacy_ids": ["ram_info"]
            },
            {
                "test_id": "IO-USB-001",
                "title": "USB inventory is collectible",
                "feature_area": "USB",
                "priority": "P2",
                "owner": "DQA",
                "intent": "Collect USB topology and attached device evidence.",
                "steps": [{"type": "collect", "command": "lsusb"}],
                "evidence_requirements": ["usb_devices"],
                "legacy_ids": ["usb_info"]
            }
        ]
    },
    "storage.smoke": {
        "pack_id": "storage.smoke",
        "name": "Storage Smoke",
        "description": "Read-only storage visibility and SMART readiness checks.",
        "requires": ["lsblk", "smartctl"],
        "test_cases": [
            {
                "test_id": "STORAGE-001",
                "title": "Boot storage visibility and health",
                "feature_area": "Storage",
                "priority": "P1",
                "owner": "DQA",
                "intent": "Confirm boot storage is visible and health evidence can be collected.",
                "steps": [
                    {"type": "collect", "command": "lsblk -J -o NAME,PATH,TYPE,SIZE,MODEL,SERIAL,TRAN,MOUNTPOINTS"},
                    {"type": "collect", "command": "smartctl --scan -j"}
                ],
                "evidence_requirements": ["block_device_inventory", "smart_health"],
                "legacy_ids": ["storage_info"]
            }
        ]
    },
    "network.link_readiness": {
        "pack_id": "network.link_readiness",
        "name": "Network Link Readiness",
        "description": "Network interface presence, link, and cabling readiness checks.",
        "requires": ["ip", "ethtool"],
        "test_cases": [
            {
                "test_id": "NET-001",
                "title": "Configured network interfaces are ready",
                "feature_area": "Network",
                "priority": "P1",
                "owner": "DQA",
                "intent": "Confirm expected network interfaces can be inspected before active traffic tests.",
                "steps": [
                    {"type": "collect", "command": "ip -j link"},
                    {"type": "collect", "command": "ethtool <iface>"}
                ],
                "evidence_requirements": ["interface_inventory", "link_status"],
                "legacy_ids": ["lan_info"]
            }
        ]
    },
    "bmc.sensor_fru": {
        "pack_id": "bmc.sensor_fru",
        "name": "BMC Sensor and FRU",
        "description": "BMC sensor and FRU evidence collection.",
        "requires": ["ipmitool"],
        "test_cases": [
            {
                "test_id": "BMC-001",
                "title": "BMC sensor and FRU snapshot",
                "feature_area": "BMC",
                "priority": "P2",
                "owner": "DQA",
                "intent": "Collect BMC sensor and FRU identity evidence.",
                "steps": [
                    {"type": "collect", "command": "ipmitool sensor"},
                    {"type": "collect", "command": "ipmitool fru"}
                ],
                "evidence_requirements": ["bmc_sensor", "bmc_fru"],
                "legacy_ids": ["sdr_info"]
            }
        ]
    }
}


def list_pack_ids() -> list[str]:
    return sorted(BUILTIN_PACKS)


def get_pack(pack_id: str) -> dict[str, Any]:
    if pack_id not in BUILTIN_PACKS:
        raise KeyError(f"Unknown pack: {pack_id}")
    return deepcopy(BUILTIN_PACKS[pack_id])
