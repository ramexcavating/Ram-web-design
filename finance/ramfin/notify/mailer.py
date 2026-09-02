"""Send the digest and weekly report. Graph sendMail from the accounts@ mailbox."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def send_digest(graph, settings, subject: str, html: str, attachments: list[tuple[str, bytes]] | None = None) -> bool:
    to = settings.notify.get("digest_to", [])
    sender = settings.notify.get("digest_from") or (to[0] if to else None)
    if not to or not sender:
        log.warning("notify.digest_to / digest_from not configured; digest not sent")
        return False
    graph.send_mail(sender, to, subject, html, attachments)
    return True
