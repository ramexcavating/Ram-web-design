"""The old ramcontracting@live.ca mailbox, read over IMAP (Outlook.com: enable IMAP + app password, or forward it)."""
from __future__ import annotations

import email
import imaplib
import logging
import os
import sqlite3
from datetime import date, timedelta
from email.header import decode_header, make_header

from .. import db
from .common import register, wanted

log = logging.getLogger(__name__)


def scan_imap(conn: sqlite3.Connection, settings, password: str | None = None, lookback_days: int = 30) -> dict[str, int]:
    cfg = settings.sources.get("legacy_imap", {})
    stats = {"found": 0, "new": 0, "errors": 0}
    if not cfg.get("enabled"):
        return stats
    pw = password or os.environ.get("LEGACY_IMAP_PASSWORD")
    if not pw:
        log.warning("legacy IMAP enabled but LEGACY_IMAP_PASSWORD not set")
        return stats
    key = f"imap:{cfg['user']}"
    since = db.get_state(conn, key) or (date.today() - timedelta(days=lookback_days)).isoformat()
    allowed = settings.sources.get("attachment_types", ["pdf", "jpg", "jpeg", "png", "heic", "xlsx", "xls", "csv"])
    M = imaplib.IMAP4_SSL(cfg.get("host", "outlook.office365.com"))
    try:
        M.login(cfg["user"], pw)
        for folder in cfg.get("folders", ["INBOX"]):
            M.select(folder, readonly=True)
            since_imap = date.fromisoformat(since[:10]).strftime("%d-%b-%Y")
            typ, data = M.search(None, f'(SINCE "{since_imap}")')
            if typ != "OK":
                continue
            for num in data[0].split():
                stats["found"] += 1
                typ, msgdata = M.fetch(num, "(RFC822)")
                if typ != "OK":
                    stats["errors"] += 1
                    continue
                msg = email.message_from_bytes(msgdata[0][1])
                subject = str(make_header(decode_header(msg.get("Subject", ""))))
                sender = email.utils.parseaddr(msg.get("From", ""))[1]
                received = msg.get("Date", "")
                for part in msg.walk():
                    fn = part.get_filename()
                    if not fn or not wanted(fn, allowed):
                        continue
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue
                    doc_id = register(conn, settings.inbox_dir, payload, str(make_header(decode_header(fn))), source=key,
                                      source_ref=msg.get("Message-ID"), sender=sender, subject=subject, received_at=received,
                                      mime=part.get_content_type())
                    if doc_id:
                        stats["new"] += 1
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001
            pass
    db.set_state(conn, key, date.today().isoformat())
    db.log_scan(conn, "ingest", key, stats["found"], stats["new"], stats["errors"])
    return stats
