from __future__ import annotations

from pathlib import Path


def parse_legacy_summary(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "source": str(path),
        "line_count": len(text.splitlines()),
        "status": "parsed_placeholder",
        "message": "Legacy summary parsing will be implemented after the v2 contract is stable.",
    }
