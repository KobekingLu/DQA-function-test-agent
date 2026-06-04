from __future__ import annotations


def priority_to_risk(priority: str) -> str:
    if priority in {"P0", "P1"}:
        return "High"
    if priority == "P2":
        return "Medium"
    return "Low"
