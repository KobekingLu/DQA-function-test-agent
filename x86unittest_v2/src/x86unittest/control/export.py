from __future__ import annotations

import zipfile
from pathlib import Path


def export_run_zip(run_dir: Path) -> Path:
    export_dir = run_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"{run_dir.name}.zip"
    with zipfile.ZipFile(export_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in run_dir.rglob("*"):
            if path.is_file() and export_path not in path.parents:
                archive.write(path, path.relative_to(run_dir))
    return export_path
