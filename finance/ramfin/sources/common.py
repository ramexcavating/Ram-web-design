"""Shared intake helper: put bytes into the inbox and register a document row, de-duplicated by content hash."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from .. import db


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip() or "file"


def register(conn: sqlite3.Connection, inbox_dir: Path, data: bytes, filename: str, source: str, source_ref: str | None = None,
             sender: str | None = None, subject: str | None = None, received_at: str | None = None, mime: str | None = None) -> int | None:
    """Return the new document id, or None if this exact content was seen before."""
    h = sha256(data)
    if conn.execute("SELECT 1 FROM documents WHERE sha256=?", (h,)).fetchone():
        return None
    inbox_dir.mkdir(parents=True, exist_ok=True)
    local = inbox_dir / f"{h[:12]}_{safe_name(filename)}"
    local.write_bytes(data)
    doc_id = db.insert(conn, "documents", dict(
        sha256=h, source=source, source_ref=source_ref, sender=sender, subject=subject, filename=filename, mime=mime,
        local_path=str(local), received_at=received_at, status="new", created_at=db.now_iso(),
    ))
    conn.commit()
    return doc_id


def wanted(filename: str, allowed: list[str]) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in [a.lower() for a in allowed]
