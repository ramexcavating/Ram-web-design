"""Put the original where it belongs. LocalFiler for tests and dry runs; SharePointFiler for the real thing."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from .rules.filing import FilingDecision


class Filer(Protocol):
    def file(self, local_path: str | Path, decision: FilingDecision) -> str: ...


class LocalFiler:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def file(self, local_path: str | Path, decision: FilingDecision) -> str:
        dest_dir = self.root / decision.library / decision.folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / decision.filename
        i = 1
        while dest.exists():
            stem, suf = dest.stem, dest.suffix
            dest = dest_dir / f"{stem}_{i}{suf}"
            i += 1
        shutil.copy2(local_path, dest)
        return str(dest)


class SharePointFiler:
    def __init__(self, graph, finance_drive_id: str, projects_drive_id: str | None = None, resources_drive_id: str | None = None):
        self.graph = graph
        self.drives = {"finance": finance_drive_id, "projects": projects_drive_id or finance_drive_id, "resources": resources_drive_id or finance_drive_id}

    def file(self, local_path: str | Path, decision: FilingDecision) -> str:
        data = Path(local_path).read_bytes()
        return self.graph.upload(self.drives[decision.library], decision.folder, decision.filename, data)
