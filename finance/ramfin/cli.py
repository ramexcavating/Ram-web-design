"""ramfin command line.

  ramfin doctor                        connection test: keys, mailboxes, SharePoint, Claude, QuickBooks
  ramfin init                          create the database, load cost codes / vendors / jobs
  ramfin auth legacy                   one-time sign-in to the old ramcontracting@live.ca mailbox (prints a code)
  ramfin db pull | push                fetch / store the database on SharePoint (runs do this automatically)
  ramfin ingest [--folder PATH]        pull new documents from mailboxes, old mailbox, CamScanner folder (or a local folder)
  ramfin process [--dry-run]           classify, extract, record, file
  ramfin bank import KEY FORMAT FILE   import a bank CSV
  ramfin balance KEY AMOUNT [--as-of]  record a bank balance (LOC: amount drawn)
  ramfin reconcile                     match bank lines, refresh actions, QBO variance
  ramfin weekly [--send]               forecast + no-breach + workbook + digest
  ramfin review IMPORT.xlsx            read your edits back from the review workbook
  ramfin inbox                         print open action items
  ramfin run-all [--send]              ingest -> process -> reconcile -> weekly (the scheduled entry point)
  ramfin backfill [--lookback-days N]  first run: index what is filed, then the full loop over N days of mail
  ramfin index-existing                register files already on SharePoint so they are never filed twice
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from . import db, pipeline
from .config import load_settings

log = logging.getLogger("ramfin")


def _conn(settings):
    return db.connect(settings.db_path)


def _graph():
    from .sources.graph import GraphClient
    return GraphClient()


def _finance_drive(settings, graph) -> str:
    sp = settings.sharepoint
    host = os.environ.get("SP_HOSTNAME", "netorg19644794.sharepoint.com")
    return graph.drive_id(graph.site_id(host, sp["site"]), sp["library"])


def _legacy_graph(settings):
    from .sources.graph import DelegatedGraphClient
    from .state_sync import TOKEN_NAME
    return DelegatedGraphClient(str(settings.data_dir / TOKEN_NAME))


def cmd_auth(a, settings):
    if a.what == "legacy":
        g = _legacy_graph(settings)
        who = g.sign_in_interactive()
        print(f"signed in as {who}; the sign-in is remembered in {settings.data_dir}. Run 'ramfin db push' so it travels with the database.")


def cmd_db(a, settings):
    from . import state_sync
    graph = _graph()
    drive = _finance_drive(settings, graph)
    if a.dbcmd == "pull":
        print(json.dumps(state_sync.pull(graph, drive, settings)))
    else:
        print(json.dumps(state_sync.push(graph, drive, settings)))


def _extractor(settings, dry_run: bool):
    if dry_run:
        from .extract.extractor import FakeExtractor
        return FakeExtractor({}, {"doc_type": "other", "confidence": 0.0, "legible": True, "notes": "dry run"})
    from .extract.extractor import ClaudeExtractor
    return ClaudeExtractor(model=settings.claude_model, max_tokens=settings.claude_max_tokens)


def _filer(settings, graph, local: bool):
    from .filer import LocalFiler, SharePointFiler
    if local or graph is None:
        return LocalFiler(settings.data_dir / "filed")
    d = _drives(settings, graph)
    return SharePointFiler(graph, d["finance"], d["projects"], d["resources"])


def cmd_doctor(a, settings):
    from . import doctor
    sys.exit(doctor.run(settings))


def _drives(settings, graph) -> dict[str, str | None]:
    """finance, projects and resources drive ids (the latter two may be unavailable)."""
    sp = settings.sharepoint
    host = os.environ.get("SP_HOSTNAME", "netorg19644794.sharepoint.com")
    out: dict[str, str | None] = {"finance": graph.drive_id(graph.site_id(host, sp["site"]), sp["library"]), "projects": None, "resources": None}
    for key, site_k, lib_k, dflt in (("projects", "projects_site", "projects_library", "PROJECTS"), ("resources", "equipment_site", "equipment_library", "RESOURCES")):
        try:
            out[key] = graph.drive_id(graph.site_id(host, sp.get(site_k, dflt)), sp.get(lib_k, dflt))
        except Exception as e:  # noqa: BLE001
            log.warning("%s drive unavailable: %s", key, e)
    return out


def cmd_init(a, settings):
    """Create or refresh the database from config and the workbooks on SharePoint. Safe to re-run."""
    from . import seed, state_sync
    graph = None if a.local else _graph()
    drives = _drives(settings, graph) if graph else {}
    if graph:
        print("pull:", json.dumps(state_sync.pull(graph, drives["finance"], settings)))
    conn = _conn(settings)
    out = {"reference_csv": pipeline.load_reference_data(conn, settings), "config": seed.seed_from_config(conn, settings)}
    if graph:
        out["sharepoint"] = seed.seed_from_sharepoint(conn, settings, graph, drives["finance"], drives["projects"])
        conn.commit(); conn.close()
        out["push"] = state_sync.push(graph, drives["finance"], settings)
    print(json.dumps(out, indent=2, default=str))


def cmd_ingest(a, settings):
    conn = _conn(settings)
    stats = {}
    lookback = int(getattr(a, "lookback_days", None) or 3)
    if a.folder:
        from .sources.folder import scan_local_folder
        stats["folder"] = scan_local_folder(conn, settings, a.folder, source="folder")
    else:
        graph = _graph()
        from .sources.mailbox import scan_mailboxes
        stats["mail"] = scan_mailboxes(conn, settings, graph, lookback_days=lookback)
        leg = settings.sources.get("legacy_mailbox", {})
        if leg.get("enabled"):
            try:
                lg = _legacy_graph(settings)
                if lg.signed_in():
                    stats["legacy"] = scan_mailboxes(conn, settings, lg, lookback_days=lookback, mailboxes=["me"], label=leg.get("address", "legacy"))
                else:
                    from .notify.inbox import raise_item
                    raise_item(conn, "decision", f"Old mailbox {leg.get('address')} is not signed in", "Run: ramfin auth legacy (one-time, prints a code to enter in a browser).", "sync_state", 3, priority=2)
                    conn.commit()
            except Exception as e:  # noqa: BLE001
                log.warning("legacy mailbox scan failed: %s", e)
        from .sources.legacy_imap import scan_imap
        stats["imap"] = scan_imap(conn, settings)
        cam = settings.sources.get("camscanner_folder")
        if cam:
            from .sources.folder import scan_sharepoint_folder
            sp = settings.sharepoint
            host = os.environ.get("SP_HOSTNAME", "netorg19644794.sharepoint.com")
            drive = _drives(settings, graph)["finance"]
            stats["camscanner"] = scan_sharepoint_folder(conn, settings, graph, drive, cam)
    print(json.dumps(stats, indent=2))


def cmd_process(a, settings):
    conn = _conn(settings)
    graph = None if (a.dry_run or a.local) else _graph()
    refetch = None
    if graph is not None:
        from .sources.common import refetch_bytes
        graphs = {"app": graph, "me": None, "finance_drive": _drives(settings, graph)["finance"]}
        try:
            lg = _legacy_graph(settings)
            graphs["me"] = lg if lg.signed_in() else None
        except Exception:  # noqa: BLE001
            pass
        refetch = lambda d: refetch_bytes(conn, settings, d, graphs)  # noqa: E731
    stats = pipeline.process_new_documents(conn, settings, _extractor(settings, a.dry_run), _filer(settings, graph, a.local or a.dry_run),
                                           limit=int(getattr(a, "limit", None) or 200), refetch=refetch)
    print(json.dumps(stats, indent=2))


def cmd_bank(a, settings):
    conn = _conn(settings)
    from .sources.bank_import import import_csv
    text = Path(a.file).read_text(encoding="utf-8-sig", errors="replace")
    found, new = import_csv(conn, a.key, a.format, text, statement_ref=Path(a.file).name)
    print(f"{a.key}: {new} new of {found} lines")


def cmd_balance(a, settings):
    conn = _conn(settings)
    db.upsert_ignore(conn, "bank_balances", dict(as_of=a.as_of or date.today().isoformat(), account_key=a.key, balance=float(a.amount), source="manual", created_at=db.now_iso()))
    conn.commit()
    print(f"recorded {a.key} = {float(a.amount):,.2f} as of {a.as_of or date.today().isoformat()}")


def cmd_reconcile(a, settings):
    conn = _conn(settings)
    qbo = None
    if os.environ.get("QBO_REFRESH_TOKEN"):
        from .sources.qbo import QBOClient
        qbo = QBOClient()
    print(json.dumps(pipeline.reconcile(conn, settings, qbo), indent=2, default=str))


def cmd_weekly(a, settings):
    conn = _conn(settings)
    out = pipeline.weekly(conn, settings, settings.data_dir / "reports", apply_deferrals=not a.no_deferrals)
    print(out["report"]["headline"])
    print(f"workbook: {out['xlsx']}\nreport:   {out['docx']}")
    if a.send:
        from .notify.mailer import send_digest
        graph = _graph()
        att = [(Path(out["xlsx"]).name, Path(out["xlsx"]).read_bytes()), (Path(out["docx"]).name, Path(out["docx"]).read_bytes())]
        print("digest sent" if send_digest(graph, settings, out["digest_subject"], out["digest_html"], att) else "digest NOT sent")
        if not a.local:
            filer = _filer(settings, graph, False)
            from .rules.filing import FilingDecision
            sp = settings.sharepoint
            filer.file(out["xlsx"], FilingDecision(sp["cashflow"], Path(out["xlsx"]).name), replace=True)
            filer.file(out["docx"], FilingDecision(f"{sp['cashflow']}/01_WEEKLY_MANAGERS_REPORT", Path(out["docx"]).name), replace=True)


def cmd_review(a, settings):
    conn = _conn(settings)
    from .reports.import_decisions import import_workbook
    print(json.dumps(import_workbook(conn, a.file), indent=2))
    from .notify.inbox import auto_resolve
    print(f"auto-resolved {auto_resolve(conn)} action item(s)")


def cmd_resolve(a, settings):
    conn = _conn(settings)
    from .notify.inbox import resolve
    conn.execute("UPDATE action_items SET detail=COALESCE(detail,'') || ? WHERE id=?", (f"\nAnswer: {a.answer}" if a.answer else "", a.id))
    resolve(conn, a.id)
    print(f"resolved #{a.id}")


def cmd_inbox(a, settings):
    conn = _conn(settings)
    from .notify.inbox import open_items
    for it in open_items(conn):
        print(f"[{ {1:'TODAY',2:'WEEK',3:'LATER'}[it['priority']] }] #{it['id']} {it['title']}")
        if a.verbose and it["detail"]:
            print("      " + it["detail"].replace("\n", "\n      "))


def cmd_index_existing(a, settings):
    """Hash what is already filed on SharePoint so the backfill does not file it twice."""
    from .sources.folder import index_existing
    conn = _conn(settings)
    graph = _graph()
    d = _drives(settings, graph)
    sp = settings.sharepoint
    folders = [sp["receipts"], sp["ap_invoices"], sp["timesheets"], sp["bank_statements"], sp["qb_reports"]]
    print(json.dumps(index_existing(conn, settings, graph, d["finance"], folders), indent=2))


def cmd_backfill(a, settings):
    """First real run: pull state, index what is filed, ingest N days, process, reconcile, weekly (+send), push state."""
    a.dbcmd = "pull"; cmd_db(a, settings)
    cmd_index_existing(a, settings)
    a.folder = None
    cmd_ingest(a, settings)
    a.dry_run, a.local = False, False
    cmd_process(a, settings)
    cmd_reconcile(a, settings)
    a.no_deferrals = False
    cmd_weekly(a, settings)
    a.dbcmd = "push"; cmd_db(a, settings)


def cmd_run_all(a, settings):
    if not a.local:
        a.dbcmd = "pull"; cmd_db(a, settings)
    a.folder = None
    a.lookback_days = getattr(a, "lookback_days", 3)
    a.limit = getattr(a, "limit", 200)
    cmd_ingest(a, settings)
    a.dry_run, a.local = False, a.local
    cmd_process(a, settings)
    cmd_reconcile(a, settings)
    a.no_deferrals = False
    cmd_weekly(a, settings)
    if not a.local:
        a.dbcmd = "push"; cmd_db(a, settings)


def main(argv=None):
    logging.basicConfig(level=os.environ.get("RAMFIN_LOG", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="ramfin", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", help="path to config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    s = sub.add_parser("init"); s.add_argument("--local", action="store_true"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("auth"); s.add_argument("what", choices=["legacy"]); s.set_defaults(fn=cmd_auth)
    s = sub.add_parser("db"); s.add_argument("dbcmd", choices=["pull", "push"]); s.set_defaults(fn=cmd_db)
    s = sub.add_parser("ingest"); s.add_argument("--folder"); s.add_argument("--lookback-days", type=int, default=3); s.set_defaults(fn=cmd_ingest)
    s = sub.add_parser("process"); s.add_argument("--dry-run", action="store_true"); s.add_argument("--limit", type=int, default=200); s.add_argument("--local", action="store_true", help="file into data/filed instead of SharePoint"); s.set_defaults(fn=cmd_process)
    s = sub.add_parser("bank"); s2 = s.add_subparsers(dest="bankcmd", required=True); si = s2.add_parser("import")
    si.add_argument("key"); si.add_argument("format", choices=["rbc_csv", "td_csv", "capitalone_csv", "generic_csv"]); si.add_argument("file"); si.set_defaults(fn=cmd_bank)
    s = sub.add_parser("balance"); s.add_argument("key"); s.add_argument("amount"); s.add_argument("--as-of"); s.set_defaults(fn=cmd_balance)
    sub.add_parser("reconcile").set_defaults(fn=cmd_reconcile)
    s = sub.add_parser("weekly"); s.add_argument("--send", action="store_true"); s.add_argument("--local", action="store_true"); s.add_argument("--no-deferrals", action="store_true"); s.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS); s.set_defaults(fn=cmd_weekly)
    s = sub.add_parser("review"); s.add_argument("file"); s.set_defaults(fn=cmd_review)
    s = sub.add_parser("resolve"); s.add_argument("id", type=int); s.add_argument("answer", nargs="?", default=""); s.set_defaults(fn=cmd_resolve)
    s = sub.add_parser("inbox"); s.add_argument("-v", "--verbose", action="store_true"); s.set_defaults(fn=cmd_inbox)
    sub.add_parser("index-existing").set_defaults(fn=cmd_index_existing)
    s = sub.add_parser("backfill"); s.add_argument("--send", action="store_true"); s.add_argument("--lookback-days", type=int, default=45); s.add_argument("--limit", type=int, default=300); s.set_defaults(fn=cmd_backfill)
    s = sub.add_parser("run-all"); s.add_argument("--send", action="store_true"); s.add_argument("--local", action="store_true"); s.add_argument("--lookback-days", type=int, default=3); s.add_argument("--limit", type=int, default=200); s.set_defaults(fn=cmd_run_all)
    a = p.parse_args(argv)
    settings = load_settings(a.config)
    a.fn(a, settings)


if __name__ == "__main__":
    sys.exit(main())
