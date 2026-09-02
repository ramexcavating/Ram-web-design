"""Supplier statement versus register: the newer document wins.

register recency for a vendor = the latest of (updated_at, invoice_date, created_at) over its open rows. updated_at is
set whenever Rodney edits a row in the review workbook, so a hand correction always outranks an older statement.

If the statement is newer:
  with itemised lines  -> rows on the statement stay (amount corrected to the statement), rows missing from it are
                          marked Paid as of the statement date, lines not yet on the register are added as Unpaid.
  total only          -> the open rows collapse into one row carrying the statement balance, keeping the earliest
                          planned pay date Rodney had set; the superseded invoice numbers go in the note.
If the statement is older: nothing changes; a low-priority note records that it was seen.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import timedelta

from .. import db
from ..models import Extraction
from ..notify.inbox import raise_item
from .filing import parse_date

OPEN = ("Unpaid", "Scheduled", "Partially Paid", "Deferred (no-breach)")
INV_RX = re.compile(r"\b([A-Z]{0,3}-?\d{3,10}[A-Z]?)\b")


def register_recency(conn: sqlite3.Connection, vendor_id: int) -> str | None:
    r = conn.execute("SELECT MAX(COALESCE(updated_at, invoice_date, created_at)) m FROM ap_invoices WHERE vendor_id=? AND status IN (%s)" % ",".join("?" * len(OPEN)),
                     (vendor_id, *OPEN)).fetchone()
    return (r["m"] or "")[:10] or None


def reconcile_statement(conn: sqlite3.Connection, vendor_id: int, ex: Extraction, doc_id: int) -> str:
    vname = conn.execute("SELECT name FROM vendors WHERE id=?", (vendor_id,)).fetchone()["name"]
    stmt_date = parse_date(ex.statement_end) or parse_date(ex.doc_date)
    if not stmt_date:
        return f"statement {vname}: no date, left alone"
    balance = round(float(ex.total), 2)
    rows = db.rows(conn, "SELECT * FROM ap_invoices WHERE vendor_id=? AND status IN (%s) ORDER BY COALESCE(invoice_date, created_at)" % ",".join("?" * len(OPEN)), (vendor_id, *OPEN))
    register_total = round(sum(float(r["amount"] or 0) for r in rows), 2)
    recency = register_recency(conn, vendor_id)
    sd = stmt_date.isoformat()
    if abs(balance - register_total) < 1.0:
        return f"statement {vname} ${balance:,.2f} agrees with the register"
    if recency and sd < recency:
        raise_item(conn, "decision", f"{vname}: statement dated {sd} (${balance:,.2f}) is older than the register's last change ({recency}); left as is",
                   f"Register open total ${register_total:,.2f}. Nothing changed because the register was updated after this statement.", "vendors", vendor_id, priority=3)
        return f"statement {vname} older than register: left alone"

    lines = [(li.description or "", li.amount) for li in ex.line_items if (li.description or "").strip()]
    itemised = {}
    for desc, amt in lines:
        m = INV_RX.findall(desc.upper())
        if m and amt is not None:
            itemised[m[-1]] = (desc, float(amt))
    changed = []
    if itemised and len(itemised) >= max(1, len(rows) // 2):
        kept = set()
        for r in rows:
            key = re.sub(r"[^A-Z0-9-]", "", (r["invoice_no"] or "").upper())
            hit = next((k for k in itemised if k and (k in key or key in k)), None)
            if hit:
                kept.add(hit)
                amt = itemised[hit][1]
                if abs(amt) > 0 and abs(float(r["amount"] or 0) - amt) > 0.005:
                    conn.execute("UPDATE ap_invoices SET amount=?, amount_confirmed=1, updated_at=? WHERE id=?", (abs(amt), db.now_iso(), r["id"]))
                    changed.append(f"{r['invoice_no']} amount -> {abs(amt):,.2f}")
            else:
                conn.execute("UPDATE ap_invoices SET status='Paid', paid_date=?, method='per statement', updated_at=?, notes=COALESCE(notes,'') || ? WHERE id=?",
                             (sd, db.now_iso(), f" [auto: not on {vname} statement {sd}; treated as paid]", r["id"]))
                changed.append(f"{r['invoice_no']} not on statement -> Paid")
        for k, (desc, amt) in itemised.items():
            if k not in kept and amt > 0 and not conn.execute("SELECT 1 FROM ap_invoices WHERE vendor_id=? AND invoice_no=?", (vendor_id, k)).fetchone():
                due = (stmt_date + timedelta(days=30)).isoformat()
                db.insert(conn, "ap_invoices", dict(vendor_id=vendor_id, invoice_no=k, invoice_date=sd, due_date=due, amount=amt, amount_confirmed=1, status="Unpaid",
                                                    planned_pay_date=due, document_id=doc_id, category="supplier", notes=f"added from {vname} statement {sd}: {desc[:120]}", created_at=db.now_iso(), updated_at=db.now_iso()))
                changed.append(f"{k} added {amt:,.2f}")
        mode = "itemised"
    else:
        earliest_plan = min((r["planned_pay_date"] for r in rows if r["planned_pay_date"]), default=(stmt_date + timedelta(days=30)).isoformat())
        superseded = [r["invoice_no"] for r in rows]
        for r in rows:
            conn.execute("UPDATE ap_invoices SET status='Reference only', planned_pay_date=NULL, updated_at=?, notes=COALESCE(notes,'') || ? WHERE id=?",
                         (db.now_iso(), f" [auto: superseded by {vname} statement {sd}]", r["id"]))
        if balance > 0:
            db.insert(conn, "ap_invoices", dict(vendor_id=vendor_id, invoice_no=f"STMT {sd}", invoice_date=sd, due_date=earliest_plan, amount=balance, amount_confirmed=1,
                                                status="Unpaid", planned_pay_date=earliest_plan, document_id=doc_id, category="supplier",
                                                notes=f"statement balance {sd}; replaces {', '.join(str(x) for x in superseded) or 'no prior rows'}", created_at=db.now_iso(), updated_at=db.now_iso()))
        changed.append(f"{len(rows)} rows collapsed into statement balance {balance:,.2f}")
        mode = "total only"
    conn.commit()
    raise_item(conn, "decision", f"{vname}: register updated from statement {sd} (${register_total:,.2f} -> ${balance:,.2f})",
               f"Newer document wins. Changes: {'; '.join(changed)[:600]}", "vendors", vendor_id, priority=3)
    return f"statement {vname} {sd} applied ({mode}): {len(changed)} change(s)"
