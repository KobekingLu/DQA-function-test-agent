from __future__ import annotations

from pathlib import Path


class RemoteAdapter:
    name = "remote"

    def __init__(self, target_config: Path) -> None:
        self.target_config = target_config

    def describe(self) -> dict[str, str]:
        return {
            "adapter": self.name,
            "target_config": str(self.target_config),
            "status": "planned",
            "message": "SSH execution will be wired to the existing dqa_remote_run flow next.",
        }
