from __future__ import annotations


LABELS = {
    "overview": "Overview / 總覽",
    "decision": "Decision / 判定",
    "coverage": "Coverage / 覆蓋率",
    "preflight": "Preflight / 前置檢查",
    "actions": "Action Items / 後續行動",
    "ready": "Ready for Exit / 可進入結案",
    "retest": "Retest Required / 需要複測",
    "block": "Block Release / 阻擋 Release",
}


def label(key: str) -> str:
    return LABELS.get(key, key)
