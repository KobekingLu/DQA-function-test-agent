from __future__ import annotations

from typing import Any


def pick_owner(items: list[dict[str, Any]]) -> str:
    for item in items:
        owner = str(item.get("owner", "")).strip()
        if owner:
            return owner
    return "DQA"
