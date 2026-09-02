"""Folder sources: a local directory (OneDrive-synced CamScanner export, a scanner drop folder, a USB stick)
or a SharePoint folder read through Graph."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .. import db
from .common import register, wanted

log = logging.getLogger(__name__)


def scan_local_folder(conn: sqlite3.Connection, settings, path: str | Path, source: str = "folder", allowed: list[str] | None = None) -> dict[str, int]:
    p = Path(path)
    stats = {"found": 0, "new": 0, "errors": 0}
    if not p.exists():
        return stats
    allowed = allowed or settings.sources.get("attachment_types", ["pdf", "jpg", "jpeg", "png", "heic"])
    for f in sorted(p.rglob("*")):
        if not f.is_file() or not wanted(f.name, allowed):
            continue
        stats["found"] += 1
        try:
            doc_id = register(conn, settings.inbox_dir, f.read_bytes(), f.name, source=source, source_ref=str(f),
                              received_at=None)
            if doc_id:
                stats["new"] += 1
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            log.warning("folder read failed %s: %s", f, e)
    db.log_scan(conn, "ingest", f"{source}:{p}", stats["found"], stats["new"], stats["errors"])
    return stats


def scan_sharepoint_folder(conn: sqlite3.Connection, settings, graph, drive_id: str, folder_path: str, source: str = "camscanner") -> dict[str, int]:
    stats = {"found": 0, "new": 0, "errors": 0}
    allowed = settings.sources.get("attachment_types", ["pdf", "jpg", "jpeg", "png", "heic"])
    try:
        for item in graph.list_children(drive_id, folder_path):
            if "file" not in item or not wanted(item["name"], allowed):
                continue
            stats["found"] += 1
            if conn.execute("SELECT 1 FROM documents WHERE source=? AND source_ref=?", (source, item["id"])).fetchone():
                continue
            data = graph.download_item(drive_id, item["id"])
            doc_id = register(conn, settings.inbox_dir, data, item["name"], source=source, source_ref=item["id"],
                              received_at=item.get("createdDateTime"), mime=item["file"].get("mimeType"))
            if doc_id:
                stats["new"] += 1
    except Exception as e:  # noqa: BLE001
        stats["errors"] += 1
        log.error("sharepoint folder scan failed %s: %s", folder_path, e)
    db.log_scan(conn, "ingest", f"{source}:{folder_path}", stats["found"], stats["new"], stats["errors"])
    return stats
