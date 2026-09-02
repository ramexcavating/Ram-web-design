"""The database and the sign-in cache live on SharePoint between runs, next to the cash flow tool, with the same
permissions. Pull at the start of a run, push at the end. A GitHub runner, the office PC or a Claude session can
therefore run the system interchangeably: whoever runs last, wins, and there is one copy."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)
DB_NAME = "ramfin.sqlite"
TOKEN_NAME = "legacy_token_cache.json"


def pull(graph, drive_id: str, settings) -> dict[str, bool]:
    folder = settings.sharepoint["state"]
    out = {}
    for name, dest in ((DB_NAME, settings.db_path), (TOKEN_NAME, settings.data_dir / TOKEN_NAME)):
        data = graph.download_path(drive_id, f"{folder}/{name}")
        if data:
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(data)
        out[name] = bool(data)
    return out


def push(graph, drive_id: str, settings) -> dict[str, str]:
    folder = settings.sharepoint["state"]
    out = {}
    if settings.db_path.exists():
        # a consistent snapshot even if WAL has uncheckpointed pages
        snap = settings.data_dir / f"{DB_NAME}.snapshot"
        src = sqlite3.connect(settings.db_path)
        dst = sqlite3.connect(snap)
        src.backup(dst)
        dst.close(); src.close()
        out[DB_NAME] = graph.upload_replace(drive_id, folder, DB_NAME, snap.read_bytes())
        snap.unlink(missing_ok=True)
    tok = settings.data_dir / TOKEN_NAME
    if tok.exists():
        out[TOKEN_NAME] = graph.upload_replace(drive_id, folder, TOKEN_NAME, tok.read_bytes())
    return out
