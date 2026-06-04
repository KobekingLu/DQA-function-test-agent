from __future__ import annotations

from typing import Any

from .. import __version__
from ..domain.models import RunContext


def build_manifest(context: RunContext, profile: dict[str, Any], collect_only: bool) -> dict[str, Any]:
    return {
        "schema_version": "x86unittest.manifest.v1",
        "tool_version": __version__,
        "run_id": context.run_id,
        "started_at": context.started_at,
        "profile_id": profile["profile_id"],
        "product_name": profile.get("product_name", ""),
        "collect_only": collect_only,
        "remote": profile.get("remote", {}),
    }
