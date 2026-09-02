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


def refetch_bytes(conn: sqlite3.Connection, settings, doc, graphs: dict) -> bool:
    """The inbox copy of a document is gone (a fresh runner). Get the bytes again from where they came from.
    graphs: {"app": GraphClient, "me": DelegatedGraphClient | None, "finance_drive": str}. Returns True when restored."""
    src, ref = doc["source"] or "", doc["source_ref"] or ""
    data = None
    try:
        if src.startswith("mail:") and ref:
            addr = src.split(":", 1)[1]
            legacy = settings.sources.get("legacy_mailbox", {}).get("address", "")
            if addr.lower() == legacy.lower():
                g, mbx = graphs.get("me"), "me"
            else:
                g, mbx = graphs.get("app"), addr
            if g is None:
                return False
            msg = g.find_message(mbx, ref)
            if not msg:
                return False
            for att in g.list_attachments(mbx, msg["id"]):
                if att.get("name") == doc["filename"]:
                    cand = g.download_attachment(mbx, msg["id"], att["id"])
                    if sha256(cand) == doc["sha256"]:
                        data = cand
                        break
            if data is None and doc["mime"] == "text/html":
                return False
        elif src in ("camscanner", "sharepoint") and ref and graphs.get("app"):
            cand = graphs["app"].download_item(graphs["finance_drive"], ref)
            if sha256(cand) == doc["sha256"]:
                data = cand
    except Exception:  # noqa: BLE001
        return False
    if data is None:
        return False
    local = Path(doc["local_path"]) if doc["local_path"] else settings.inbox_dir / f"{doc['sha256'][:12]}_{safe_name(doc['filename'])}"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    conn.execute("UPDATE documents SET local_path=? WHERE id=?", (str(local), doc["id"]))
    conn.commit()
    return True
