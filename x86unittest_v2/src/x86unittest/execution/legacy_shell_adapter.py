from __future__ import annotations

from pathlib import Path


class LegacyShellAdapter:
    name = "legacy_shell"

    def __init__(self, legacy_root: Path) -> None:
        self.legacy_root = legacy_root

    def describe(self) -> dict[str, str]:
        return {
            "adapter": self.name,
            "legacy_root": str(self.legacy_root),
            "status": "planned",
            "message": "Legacy shell execution is intentionally isolated behind this adapter.",
        }
