from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_profile(profile_ref: str) -> dict[str, Any]:
    path = resolve_profile_path(profile_ref)
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_profile(data)
    return data


def resolve_profile_path(profile_ref: str) -> Path:
    candidate = Path(profile_ref)
    if candidate.exists():
        return candidate
    default_dir = Path(__file__).resolve().parent / "defaults"
    default_path = default_dir / f"{profile_ref}.json"
    if default_path.exists():
        return default_path
    known = ", ".join(sorted(path.stem for path in default_dir.glob("*.json")))
    raise FileNotFoundError(f"Profile not found: {profile_ref}. Known profiles: {known}")


def validate_profile(profile: dict[str, Any]) -> None:
    required = ["profile_id", "product_name", "enabled_packs"]
    missing = [key for key in required if key not in profile]
    if missing:
        raise ValueError(f"Profile is missing required fields: {', '.join(missing)}")
