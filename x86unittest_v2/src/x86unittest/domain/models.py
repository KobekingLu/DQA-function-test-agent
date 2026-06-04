from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass(frozen=True)
class TestCase:
    test_id: str
    title: str
    feature_area: str
    priority: str = "P2"
    owner: str = "DQA"
    intent: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    legacy_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TestPack:
    pack_id: str
    name: str
    description: str
    requires: list[str] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_dir: Any
    started_at: str


def to_plain_data(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_plain_data(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_plain_data(item) for item in value]
    return value
