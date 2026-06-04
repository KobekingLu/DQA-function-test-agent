from __future__ import annotations

from pathlib import Path


def load_resume_marker(run_dir: Path) -> dict[str, str]:
    marker = run_dir / "resume.json"
    if not marker.exists():
        return {"status": "not_available", "message": "No resume marker exists for this run."}
    return {"status": "available", "path": str(marker)}
