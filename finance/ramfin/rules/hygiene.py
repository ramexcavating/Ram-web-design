"""Data-quality rules applied every reconcile. Each one is a mistake the first real run made visible.

1. Historical documents. A 2021 repair invoice forwarded to accounts@ in August is a record, not a payable. Anything
   whose invoice date is more than 180 days old when it arrives becomes 'Reference only' instead of 'Unpaid'.
2. Backing documents. A daily force-account sheet (DFA) or a progress-claim breakdown supports an invoice; it is not
   an invoice. Rows whose number looks like <job>-<seq> or whose document name says DFA are marked 'Backing doc' and
   excluded from AR.
3. Superseded combined rows. A seeded tracker row like 'INV 597/598/599' is replaced when the individual invoices
   arrive; the combined row is marked 'Superseded' and a decision item asks Rodney to confirm the amounts agree.
"""
from __future__ import annotations

import re
import sqlite3

from .. import db
from ..notify.inbox import raise_item

HISTORICAL_DAYS = 180
BACKING_RX = re.compile(r"^\d{6}-\d{1,3}[A-Z]?$")          # 240617-20
BACKING_NAME_RX = re.compile(r"\bDFA\b|force[ _-]?account|daily (sheet|report)|time ?and ?material", re.I)


def historical_ap(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "UPDATE ap_invoices SET status='Reference only', planned_pay_date=NULL, notes=COALESCE(notes,'') || ' [auto: historical document, invoice older than 180 days at intake]' "
        "WHERE status IN ('Unpaid','Scheduled') AND invoice_date IS NOT NULL AND invoice_date < date('now', ?) AND document_id IS NOT NULL "
        "AND COALESCE(notes,'') NOT LIKE '%historical document%' AND COALESCE(notes,'') NOT LIKE 'seeded%'", (f"-{HISTORICAL_DAYS} days",))
    return cur.rowcount


def backing_docs(conn: sqlite3.Connection) -> int:
    n = 0
    for r in db.rows(conn, "SELECT a.id, a.invoice_no, d.filename, d.subject FROM ar_invoices a LEFT JOIN documents d ON d.id=a.document_id WHERE a.status IN ('Open','Estimate')"):
        inv = (r["invoice_no"] or "").strip()
        name = f"{r['filename'] or ''} {r['subject'] or ''}"
        if BACKING_RX.match(inv) or BACKING_NAME_RX.search(name):
            conn.execute("UPDATE ar_invoices SET status='Backing doc', notes=COALESCE(notes,'') || ' [auto: supporting document, not an invoice]' WHERE id=?", (r["id"],))
            n += 1
    return n


def superseded_combined_ar(conn: sqlite3.Connection) -> int:
    n = 0
    for r in db.rows(conn, "SELECT id, customer, invoice_no, amount FROM ar_invoices WHERE status IN ('Open','Partially Paid') AND (invoice_no LIKE '%/%' OR invoice_no LIKE '%,%' OR invoice_no LIKE '% billing%')"):
        nums = re.findall(r"\b(\d{3,6})\b", r["invoice_no"] or "")
        if not nums:
            continue
        singles = db.rows(conn, "SELECT invoice_no, amount FROM ar_invoices WHERE customer=? AND id<>? AND status IN ('Open','Paid','Partially Paid') AND document_id IS NOT NULL", (r["customer"], r["id"]))
        matched = [s for s in singles if any(re.search(rf"\b{re.escape(num)}\b", s["invoice_no"] or "") for num in nums)]
        if len(matched) >= max(1, len(nums) - 1):
            total = round(sum(s["amount"] for s in matched), 2)
            conn.execute("UPDATE ar_invoices SET status='Superseded', notes=COALESCE(notes,'') || ? WHERE id=?",
                         (f" [auto: replaced by invoices {', '.join(s['invoice_no'] for s in matched)} totalling ${total:,.2f}]", r["id"]))
            if abs(total - float(r["amount"])) > 1.0:
                raise_item(conn, "decision", f"{r['customer']}: invoices {', '.join(s['invoice_no'] for s in matched)} total ${total:,.2f} but the tracker had ${r['amount']:,.2f}",
                           "The individual invoice PDFs replaced the combined tracker row. Confirm which figure the customer actually owes (holdback? credit? a PDF that is a draft?).",
                           "ar_invoices", r["id"], priority=1)
            n += 1
    return n


def duplicate_ar(conn: sqlite3.Connection) -> int:
    """Same customer, same amount to the cent, two Open rows: keep the one with a document, mark the other Superseded."""
    n = 0
    for r in db.rows(conn, "SELECT customer, amount, COUNT(*) c FROM ar_invoices WHERE status='Open' GROUP BY customer, amount HAVING c>1"):
        rows = db.rows(conn, "SELECT id, document_id FROM ar_invoices WHERE customer=? AND amount=? AND status='Open' ORDER BY document_id IS NULL, id", (r["customer"], r["amount"]))
        for dup in rows[1:]:
            conn.execute("UPDATE ar_invoices SET status='Superseded', notes=COALESCE(notes,'') || ' [auto: duplicate of another open invoice for the same amount]' WHERE id=?", (dup["id"],))
            n += 1
    return n


def vendor_defaults(conn: sqlite3.Connection) -> int:
    """Receipts and invoices without a job or code take the vendor's defaults; personal vendors drop out of job cost."""
    n = conn.execute("UPDATE receipts SET job_no=(SELECT default_job FROM vendors v WHERE v.id=receipts.vendor_id) WHERE job_no IS NULL AND personal=0 "
                     "AND (SELECT default_job FROM vendors v WHERE v.id=receipts.vendor_id) IS NOT NULL").rowcount
    n += conn.execute("UPDATE receipts SET cost_code=(SELECT default_cost_code FROM vendors v WHERE v.id=receipts.vendor_id) WHERE cost_code IS NULL AND personal=0 "
                      "AND (SELECT default_cost_code FROM vendors v WHERE v.id=receipts.vendor_id) IS NOT NULL").rowcount
    n += conn.execute("UPDATE ap_invoices SET job_no=(SELECT default_job FROM vendors v WHERE v.id=ap_invoices.vendor_id) WHERE job_no IS NULL "
                      "AND (SELECT default_job FROM vendors v WHERE v.id=ap_invoices.vendor_id) IS NOT NULL").rowcount
    n += conn.execute("UPDATE receipts SET personal=1, job_no=NULL, cost_code=NULL, description='[personal] not a RAM expense' WHERE personal=0 "
                      "AND vendor_id IN (SELECT id FROM vendors WHERE category='personal')").rowcount
    conn.execute("UPDATE action_items SET status='resolved', resolved_at=? WHERE status='open' AND kind IN ('uncoded_receipt','illegible') AND ref_table='receipts' "
                 "AND (CASE WHEN ref_id >= 1000000 THEN ref_id - 1000000 ELSE ref_id END) IN (SELECT id FROM receipts WHERE personal=1)", (db.now_iso(),))
    return n


def replay_statements(conn: sqlite3.Connection) -> int:
    """Apply the newer-document-wins rule to statements that were read before the rule existed (newest per vendor)."""
    import json
    from ..models import Extraction
    from ..rules import vendors as vend
    from .statements import reconcile_statement
    n = 0
    seen: set[int] = set()
    for d in db.rows(conn, "SELECT id, extracted_json, sender FROM documents WHERE doc_type='vendor_statement' AND extracted_json IS NOT NULL ORDER BY json_extract(extracted_json,'$.doc_date') DESC, id DESC"):
        ex = Extraction.from_dict(json.loads(d["extracted_json"]))
        vid = vend.find_or_create(conn, ex.vendor_name, d["sender"])
        if not vid or vid in seen or ex.total is None:
            continue
        seen.add(vid)
        if conn.execute("SELECT 1 FROM action_items WHERE kind='decision' AND ref_table='vendors' AND ref_id=? AND title LIKE '%register updated from statement%'", (vid,)).fetchone():
            continue
        out = reconcile_statement(conn, vid, ex, d["id"])
        if "applied" in out:
            n += 1
            conn.execute("UPDATE action_items SET status='resolved', resolved_at=? WHERE status='open' AND kind='decision' AND ref_table='vendors' AND ref_id=? AND title LIKE '%statement says%'",
                         (db.now_iso(), vid))
    return n


def apply(conn: sqlite3.Connection) -> dict[str, int]:
    out = {"historical_ap": historical_ap(conn), "backing_docs": backing_docs(conn), "superseded_combined_ar": superseded_combined_ar(conn), "duplicate_ar": duplicate_ar(conn),
           "vendor_defaults": vendor_defaults(conn), "statements_replayed": replay_statements(conn)}
    conn.commit()
    return out
