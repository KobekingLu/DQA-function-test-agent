from __future__ import annotations

from pathlib import Path

from ..report.json_writer import read_json


def read_known_issues(path: Path) -> dict:
    return read_json(path)
