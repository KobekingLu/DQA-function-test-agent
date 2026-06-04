from __future__ import annotations

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
SKIP = "SKIP"
NOT_RUN = "NOT_RUN"
WARN = "WARN"

TERMINAL_STATUSES = {PASS, FAIL, BLOCKED, SKIP, NOT_RUN, WARN}


def normalize_status(value: str | None) -> str:
    status = (value or "").strip().upper()
    if status in TERMINAL_STATUSES:
        return status
    return WARN if status else NOT_RUN
