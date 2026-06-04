from __future__ import annotations

from .command_runner import CommandResult, run_command


class LocalAdapter:
    name = "local"

    def run(self, command: list[str], timeout: int = 60) -> CommandResult:
        return run_command(command, timeout=timeout)
