"""Connection test. Proves each key works and each mailbox and folder is reachable, without touching any data.
Prints a plain report; exits 1 if Microsoft Graph fails (nothing else works without it)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone


def run(settings) -> int:
    ok = True
    lines: list[str] = []

    def row(status: str, what: str, detail: str = "") -> None:
        lines.append(f"[{status:^4}] {what}" + (f": {detail}" if detail else ""))

    for name in ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET"):
        row("ok" if os.environ.get(name) else "MISS", f"secret {name}", "" if os.environ.get(name) else "not set")
        ok = ok and bool(os.environ.get(name))
    for name in ("ANTHROPIC_API_KEY", "QBO_REFRESH_TOKEN"):
        row("ok" if os.environ.get(name) else "skip", f"secret {name}", "" if os.environ.get(name) else "not set yet (fine for now)")

    graph = None
    if ok:
        try:
            from .sources.graph import GraphClient
            graph = GraphClient()
            graph.token()
            row("ok", "Microsoft sign-in", "app credentials accepted")
        except Exception as e:  # noqa: BLE001
            row("FAIL", "Microsoft sign-in", str(e)[:300]); ok = False

    if graph:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for mbx in settings.sources.get("mailboxes", []):
            try:
                folder = graph.get(f"/users/{mbx}/mailFolders/inbox?$select=totalItemCount")
                recent = sum(1 for _ in graph.list_messages(mbx, since))
                row("ok", f"mailbox {mbx}", f"{folder.get('totalItemCount', '?')} in inbox, {recent} received in the last 7 days")
            except Exception as e:  # noqa: BLE001
                row("FAIL", f"mailbox {mbx}", str(e)[:300]); ok = False
        sp = settings.sharepoint
        host = os.environ.get("SP_HOSTNAME", "netorg19644794.sharepoint.com")
        for label, site, lib, check in (("finance", sp["site"], sp["library"], sp["receipts"]), ("projects", sp.get("projects_site", "PROJECTS"), sp.get("projects_library", "PROJECTS"), sp.get("projects_active", ""))):
            try:
                drive = graph.drive_id(graph.site_id(host, site), lib)
                item = graph.get_item_by_path(drive, check) if check else None
                n = sum(1 for _ in graph.list_children(drive, check)) if item else 0
                row("ok", f"SharePoint {label} library", f"{lib} reachable; {check}: {'found, ' + str(n) + ' items' if item else 'NOT FOUND'}")
            except Exception as e:  # noqa: BLE001
                row("FAIL", f"SharePoint {label} library", str(e)[:300]); ok = False
        try:
            from .sources.graph import DelegatedGraphClient
            from . import state_sync
            drive = graph.drive_id(graph.site_id(host, sp["site"]), sp["library"])
            state_sync.pull(graph, drive, settings)          # the sign-in cache lives on SharePoint between runs
            lg = DelegatedGraphClient(str(settings.data_dir / state_sync.TOKEN_NAME))
            if lg.signed_in():
                inbox = lg.get("/me/mailFolders/inbox?$select=totalItemCount")
                row("ok", "old mailbox (ramcontracting@live.ca)", f"signed in, {inbox.get('totalItemCount', '?')} in inbox")
            else:
                row("todo", "old mailbox (ramcontracting@live.ca)", "not signed in yet: ramfin auth legacy")
        except Exception as e:  # noqa: BLE001
            row("todo", "old mailbox", str(e)[:200])

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            c = anthropic.Anthropic()
            r = c.messages.create(model=settings.claude_model, max_tokens=20, messages=[{"role": "user", "content": "Reply with the single word OK."}])
            row("ok", "Claude", f"{settings.claude_model} answered")
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            hint = " -> add prepaid credits at console.anthropic.com, Plans & Billing" if "credit balance" in msg else ""
            row("FAIL", "Claude", msg[:300] + hint); ok = False
    if os.environ.get("QBO_REFRESH_TOKEN"):
        try:
            from .sources.qbo import QBOClient
            QBOClient().token()
            row("ok", "QuickBooks", "token refreshed")
        except Exception as e:  # noqa: BLE001
            row("FAIL", "QuickBooks", str(e)[:300]); ok = False

    print("\n".join(lines))
    print("\nRESULT:", "all connections good" if ok else "something needs fixing (see FAIL rows)")
    return 0 if ok else 1
