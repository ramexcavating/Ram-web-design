"""Pull attachments (and body-only receipts) out of the Microsoft 365 mailboxes."""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import db
from .common import register, wanted

log = logging.getLogger(__name__)
BODY_RECEIPT_RX = re.compile(r"receipt|your order|payment (received|confirmation)|invoice|statement is ready|thank you for your (order|payment)", re.I)
SKIP_SENDER_RX = re.compile(r"no-reply-claude@|noreply@github|@mail\.anthropic\.com$|linkedin|indeed", re.I)


def scan_mailboxes(conn: sqlite3.Connection, settings, graph, lookback_days: int = 3) -> dict[str, int]:
    stats = {"found": 0, "new": 0, "errors": 0}
    allowed = settings.sources.get("attachment_types", ["pdf", "jpg", "jpeg", "png", "heic", "xlsx", "xls", "csv"])
    for mbx in settings.sources.get("mailboxes", []):
        key = f"mail:{mbx}"
        since = db.get_state(conn, key) or (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        newest = since
        found = new = errors = 0
        try:
            for msg in graph.list_messages(mbx, since):
                found += 1
                sender = (msg.get("from") or {}).get("emailAddress", {}).get("address", "")
                subject = msg.get("subject") or ""
                received = msg.get("receivedDateTime") or since
                newest = max(newest, received)
                if SKIP_SENDER_RX.search(sender or "") or re.search(r"Weekly (Managers|Priorities|Business|Equipment)", subject):
                    continue
                if msg.get("hasAttachments"):
                    for att in graph.list_attachments(mbx, msg["id"]):
                        if att.get("isInline") or not wanted(att.get("name", ""), allowed):
                            continue
                        try:
                            data = graph.download_attachment(mbx, msg["id"], att["id"])
                        except Exception as e:  # noqa: BLE001
                            errors += 1
                            log.warning("attachment download failed %s/%s: %s", mbx, att.get("name"), e)
                            continue
                        doc_id = register(conn, settings.inbox_dir, data, att["name"], source=key, source_ref=msg.get("internetMessageId") or msg["id"],
                                          sender=sender, subject=subject, received_at=received, mime=att.get("contentType"))
                        if doc_id:
                            new += 1
                elif BODY_RECEIPT_RX.search(subject) or BODY_RECEIPT_RX.search(msg.get("bodyPreview", "")):
                    body = (msg.get("body") or {}).get("content") or msg.get("bodyPreview") or ""
                    html = f"<!-- from: {sender} subject: {subject} received: {received} -->\n{body}"
                    doc_id = register(conn, settings.inbox_dir, html.encode("utf-8"), f"{re.sub(r'[^A-Za-z0-9]+', '_', subject)[:60]}.html",
                                      source=key, source_ref=msg.get("internetMessageId") or msg["id"], sender=sender, subject=subject,
                                      received_at=received, mime="text/html")
                    if doc_id:
                        new += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            log.error("mailbox scan failed for %s: %s", mbx, e)
        db.set_state(conn, key, newest)
        db.log_scan(conn, "ingest", key, found, new, errors)
        stats["found"] += found
        stats["new"] += new
        stats["errors"] += errors
    return stats
