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


INBOX_FOLDER = "inbox"


def pull(graph, drive_id: str, settings) -> dict:
    folder = settings.sharepoint["state"]
    out: dict = {}
    for name, dest in ((DB_NAME, settings.db_path), (TOKEN_NAME, settings.data_dir / TOKEN_NAME)):
        data = graph.download_path(drive_id, f"{folder}/{name}")
        if data:
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(data)
        out[name] = bool(data)
    n = 0
    try:
        settings.inbox_dir.mkdir(parents=True, exist_ok=True)
        for item in graph.list_children(drive_id, f"{folder}/{INBOX_FOLDER}"):
            if "file" in item and not (settings.inbox_dir / item["name"]).exists():
                (settings.inbox_dir / item["name"]).write_bytes(graph.download_item(drive_id, item["id"]))
                n += 1
    except Exception as e:  # noqa: BLE001
        log.info("no remote inbox yet (%s)", str(e)[:80])
    out["inbox_files"] = n
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
    out["inbox"] = sync_inbox(graph, drive_id, settings)
    return out


def sync_inbox(graph, drive_id: str, settings) -> dict[str, int]:
    """Unprocessed documents travel with the database; processed ones are removed from the remote inbox."""
    folder = f"{settings.sharepoint['state']}/{INBOX_FOLDER}"
    stats = {"uploaded": 0, "removed": 0}
    if not settings.db_path.exists():
        return stats
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    pending = {Path(r["local_path"]).name: r["local_path"] for r in conn.execute("SELECT local_path FROM documents WHERE status IN ('new','error') AND local_path IS NOT NULL")}
    conn.close()
    remote: dict[str, str] = {}
    try:
        remote = {it["name"]: it["id"] for it in graph.list_children(drive_id, folder) if "file" in it}
    except Exception:  # noqa: BLE001
        pass
    for name, path in pending.items():
        if name not in remote and Path(path).exists():
            graph.upload_replace(drive_id, folder, name, Path(path).read_bytes())
            stats["uploaded"] += 1
    for name, item_id in remote.items():
        if name not in pending:
            try:
                graph.delete_item(drive_id, item_id)
                stats["removed"] += 1
            except Exception as e:  # noqa: BLE001
                log.warning("could not remove remote inbox file %s: %s", name, e)
    return stats
