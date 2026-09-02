"""Orchestration. Four stages, each idempotent, each safe to re-run:

  ingest    -> pull new documents from every source into the inbox (no AI yet)
  process   -> classify + extract each new document, write ledger rows, file the original
  reconcile -> match bank lines, refresh action items, check QuickBooks variance
  report    -> build the 13-week forecast, apply the no-breach rule, write the workbook, send the digest
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

from . import db
from .extract.extractor import ExtractionError
from .ledger import intake
from .models import Extraction
from .notify import inbox
from .notify.inbox import raise_item
from .rules import filing, forecast, matching
from .rules.filing import parse_date

log = logging.getLogger(__name__)


def process_new_documents(conn: sqlite3.Connection, settings, extractor, filer, limit: int = 200) -> dict[str, int]:
    stats = {"processed": 0, "filed": 0, "needs_review": 0, "errors": 0}
    docs = db.rows(conn, "SELECT * FROM documents WHERE status IN ('new','error') ORDER BY id LIMIT ?", (limit,))
    for d in docs:
        stats["processed"] += 1
        try:
            data = Path(d["local_path"]).read_bytes()
            ctx = " | ".join(x for x in [f"from {d['sender']}" if d["sender"] else "", f"subject: {d['subject']}" if d["subject"] else "", f"source {d['source']}"] if x)
            ex = extractor.extract(data, d["filename"], ctx)
            received = parse_date((d["received_at"] or "")[:10])
            job_folder = None
            if ex.doc_type == "customer_payment":
                j = intake._norm_job(conn, None, f"{ex.customer_name or ''} {ex.notes or ''}")
                jr = conn.execute("SELECT sharepoint_folder FROM jobs WHERE job_no=?", (j,)).fetchone() if j else None
                job_folder = jr["sharepoint_folder"] if jr else None
            decision = filing.decide(ex, d["filename"], settings.sharepoint, received, job_folder)
            summary = intake.record(conn, settings, d["id"], ex, d["sender"], d["subject"])
            filed = filer.file(d["local_path"], decision)
            status = "needs_review" if decision.needs_review else "filed"
            conn.execute("UPDATE documents SET doc_type=?, status=?, filed_path=?, extracted_json=?, confidence=?, legible=?, error=NULL WHERE id=?",
                         (ex.doc_type, status, filed, __import__("json").dumps(ex.to_dict()), ex.confidence, 1 if ex.legible else 0, d["id"]))
            if decision.needs_review:
                stats["needs_review"] += 1
                if not ex.legible or ex.doc_type == "other":
                    raise_item(conn, "illegible", f"Could not read: {d['filename']}", f"{decision.reason}. Filed to 00_UNFILED_NEEDS_REVIEW. From {d['sender'] or d['source']}.",
                               "documents", d["id"], priority=3)
            stats["filed"] += 1
            conn.commit()
            log.info("doc %s %s -> %s (%s)", d["id"], d["filename"], ex.doc_type, summary)
        except ExtractionError as e:
            stats["errors"] += 1
            conn.execute("UPDATE documents SET status='error', error=? WHERE id=?", (str(e)[:500], d["id"]))
            conn.commit()
            log.warning("extraction failed for %s: %s", d["filename"], e)
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            conn.execute("UPDATE documents SET status='error', error=? WHERE id=?", (f"{type(e).__name__}: {e}"[:500], d["id"]))
            conn.commit()
            log.exception("processing failed for %s", d["filename"])
    db.log_scan(conn, "process", None, len(docs), stats["filed"], stats["errors"])
    return stats


def reconcile(conn: sqlite3.Connection, settings, qbo=None) -> dict:
    out = {"matching": matching.match_transactions(conn), "auto_resolved": inbox.auto_resolve(conn)}
    if qbo is not None:
        try:
            from .sources.qbo import check_variance
            out["qbo"] = check_variance(conn, qbo)
        except Exception as e:  # noqa: BLE001
            log.warning("QBO check failed: %s", e)
            out["qbo_error"] = str(e)
    stale = []
    for a in settings.bank_accounts:
        r = conn.execute("SELECT as_of FROM bank_balances WHERE account_key=? ORDER BY as_of DESC LIMIT 1", (a.key,)).fetchone()
        if a.kind in ("chequing", "card", "loc") and (not r or (date.today() - parse_date(r["as_of"])).days > 35):
            stale.append(a.name)
            raise_item(conn, "statement_stale", f"No recent statement or CSV for {a.name}", "Download the latest CSV from online banking and drop it in the bank folder, or forward the PDF statement to accounts@.",
                       "sync_state", abs(hash(a.key)) % 1_000_000, priority=2)
    out["stale_accounts"] = stale
    conn.commit()
    return out


def weekly(conn: sqlite3.Connection, settings, out_dir: str | Path, as_of: date | None = None, apply_deferrals: bool = True) -> dict:
    from .reports import export_xlsx, weekly as weekly_report
    fc = forecast.build_forecast(conn, settings, as_of)
    if apply_deferrals:
        fc = forecast.apply_no_breach(conn, settings, fc)
    report = weekly_report.build_report(conn, settings, fc)
    stamp = (as_of or date.today()).strftime("%y%m%d")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    xlsx = export_xlsx.export_workbook(conn, settings, fc, report, out / f"{stamp}_RAM_WEEKLY_REVIEW.xlsx")
    md = out / f"{stamp}_RAM_Weekly_Cashflow_Report.md"
    md.write_text(weekly_report.to_markdown(report), encoding="utf-8")
    subject, html = inbox.digest_html(conn, fc, report)
    db.log_scan(conn, "report", None, len(fc.weeks), fc.breach_weeks, 0, report["headline"])
    return dict(forecast=fc, report=report, xlsx=str(xlsx), markdown=str(md), digest_subject=subject, digest_html=html)


def load_reference_data(conn: sqlite3.Connection, settings) -> dict[str, int]:
    from .rules import cost_codes, vendors
    return {"cost_codes": cost_codes.load_csv(conn, settings.path("cost_codes_csv")), "vendors": vendors.load_csv(conn, settings.path("vendors_csv"))}
