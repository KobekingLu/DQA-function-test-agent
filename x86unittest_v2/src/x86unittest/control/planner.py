from __future__ import annotations

from typing import Any

from ..packs.registry import get_pack, list_pack_ids


def build_plan(profile: dict[str, Any], selected_packs: list[str]) -> dict[str, Any]:
    enabled = selected_packs or profile.get("enabled_packs", [])
    resolved_pack_ids = resolve_pack_ids(enabled)
    packs = [get_pack(pack_id) for pack_id in resolved_pack_ids]
    tests = []
    for pack in packs:
        for case in pack["test_cases"]:
            item = dict(case)
            item["pack_id"] = pack["pack_id"]
            item["pack_name"] = pack["name"]
            tests.append(item)

    return {
        "schema_version": "x86unittest.plan.v1",
        "profile_id": profile["profile_id"],
        "product_name": profile.get("product_name", ""),
        "selected_pack_ids": resolved_pack_ids,
        "packs": packs,
        "tests": tests,
        "test_count": len(tests),
    }


def resolve_pack_ids(requested: list[str]) -> list[str]:
    available = list_pack_ids()
    resolved: list[str] = []
    for value in requested:
        matches = [pack_id for pack_id in available if pack_id == value or pack_id.startswith(f"{value}.")]
        if not matches and value in available:
            matches = [value]
        for match in matches:
            if match not in resolved:
                resolved.append(match)
    return resolved
