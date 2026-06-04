from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..domain.ids import slugify
from ..domain.models import RunContext


def create_run_context(output_dir: Path, profile_id: str) -> RunContext:
    started_at = datetime.now().isoformat(timespec="seconds")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{slugify(profile_id)}_{timestamp}"
    run_dir = output_dir / run_id
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "html").mkdir(parents=True, exist_ok=True)
    return RunContext(run_id=run_id, run_dir=run_dir, started_at=started_at)
