from __future__ import annotations


def map_legacy_item_id(legacy_id: str, mapping: dict[str, str]) -> str:
    return mapping.get(legacy_id, legacy_id)
