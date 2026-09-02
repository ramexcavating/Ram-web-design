"""Turn an Extraction into ledger rows. This is where a photo of a till slip becomes a receipt on a job."""
from __future__ import annotations

import re
import sqlite3
from datetime import timedelta

from .. import db
from ..models import Extraction
from ..notify.inbox import raise_item
from ..rules import cost_codes, vendors
from ..rules.filing import parse_date
from ..sources import bank_import
from . import timesheets as ts


def _job_exists(conn: sqlite3.Connection, job_no: str | None) -> bool:
    return bool(job_no) and conn.execute("SELECT 1 FROM jobs WHERE job_no=?", (job_no,)).fetchone() is not None


def _norm_job(conn: sqlite3.Connection, raw: str | None, fallback_text: str = "") -> str | None:
    """'240617', '24-06-17', 'MDM' -> a job_no we know, else None."""
    if raw:
        digits = re.sub(r"\D", "", str(raw))
        if len(digits) == 6 and _job_exists(conn, digits):
            return digits
    text = " " + re.sub(r"[^A-Z0-9]+", " ", f"{raw or ''} {fallback_text}".upper()) + " "
    jobs = db.rows(conn, "SELECT job_no, name, client FROM jobs WHERE status='active'")
    for j in jobs:                                   # full job name or client name
        for cand in (j["name"], j["client"]):
            if cand and f" {re.sub(r'[^A-Z0-9]+', ' ', cand.upper()).strip()} " in text:
                return j["job_no"]
    firsts = [(j["job_no"], j["name"].upper().split()[0]) for j in jobs if j["name"] and len(j["name"].split()[0]) >= 3]
    hits = [jn for jn, tok in firsts if f" {tok} " in text]
    return hits[0] if len(hits) == 1 else None


def record(conn: sqlite3.Connection, settings, doc_id: int, ex: Extraction, sender: str | None = None, subject: str | None = None) -> str:
    """Dispatch on doc_type. Returns a short human summary of what was recorded."""
    fn = {
        "receipt": _receipt, "vendor_invoice": _vendor_invoice, "vendor_statement": _vendor_statement,
        "customer_payment": _customer_payment, "customer_invoice": _customer_invoice, "timesheet": _timesheet,
        "paystub": _paystub, "bank_statement": _bank_statement,
    }.get(ex.doc_type)
    if not fn:
        return f"{ex.doc_type}: filed only"
    out = fn(conn, settings, doc_id, ex, sender, subject)
    conn.commit()
    return out


def _receipt(conn, settings, doc_id, ex: Extraction, sender, subject) -> str:
    vid = vendors.find_or_create(conn, ex.vendor_name, sender)
    job = _norm_job(conn, ex.handwritten_job_no, subject or "")
    desc = "; ".join(li.description for li in ex.line_items[:5]) or (ex.notes or "")
    code, conf, why = cost_codes.suggest(conn, vid, ex.vendor_name, desc, ex.handwritten_cost_code)
    rid = db.insert(conn, "receipts", dict(
        vendor_id=vid, receipt_date=(parse_date(ex.doc_date) or parse_date(None)).isoformat() if parse_date(ex.doc_date) else None,
        amount=ex.total, gst=ex.gst, payment_method=ex.payment_method, card_last4=ex.card_last4, job_no=job,
        cost_code=code if conf >= 0.5 else None, equipment_id=equipment_unit(conn, ex), document_id=doc_id,
        legible=1 if ex.legible else 0, description=desc[:500], created_at=db.now_iso()))
    if not job:
        raise_item(conn, "uncoded_receipt", f"Receipt needs a job: {ex.vendor_name or 'unknown vendor'} ${ex.total or 0:,.2f} on {ex.doc_date or '?'}",
                   f"No job number found on the receipt (read: {ex.handwritten_job_no!r}). Pick the job in the review sheet.", "receipts", rid, priority=3)
    if conf < 0.5:
        raise_item(conn, "uncoded_receipt", f"Receipt needs a cost code: {ex.vendor_name or 'unknown vendor'} ${ex.total or 0:,.2f}",
                   f"Best guess {code or 'none'} ({why}). Confirm or pick another in the review sheet.", "receipts", rid + 1_000_000, priority=3)
    if ex.total is None:
        raise_item(conn, "illegible", f"Receipt total unreadable: {ex.vendor_name or 'unknown vendor'} {ex.doc_date or ''}",
                   "Re-photograph while the paper still exists.", "receipts", rid, priority=2)
    return f"receipt {ex.vendor_name} ${ex.total} job={job} code={code}"


def _vendor_invoice(conn, settings, doc_id, ex: Extraction, sender, subject) -> str:
    vid = vendors.find_or_create(conn, ex.vendor_name, sender)
    v = conn.execute("SELECT * FROM vendors WHERE id=?", (vid,)).fetchone() if vid else None
    inv_date = parse_date(ex.doc_date)
    due = parse_date(ex.due_date) or (inv_date + timedelta(days=int(v["default_terms_days"] if v else 30)) if inv_date else None)
    job = _norm_job(conn, ex.handwritten_job_no, f"{subject or ''} {ex.notes or ''} " + " ".join(li.description for li in ex.line_items))
    desc = "; ".join(li.description for li in ex.line_items[:5]) or (ex.notes or "")
    code, conf, _ = cost_codes.suggest(conn, vid, ex.vendor_name, desc, ex.handwritten_cost_code)
    inv_no = (ex.invoice_no or f"DOC{doc_id}").strip()
    existing = conn.execute("SELECT id FROM ap_invoices WHERE vendor_id=? AND invoice_no=?", (vid, inv_no)).fetchone()
    if existing:
        conn.execute("UPDATE ap_invoices SET amount=COALESCE(?, amount), gst=COALESCE(?, gst), amount_confirmed=CASE WHEN ? IS NOT NULL THEN 1 ELSE amount_confirmed END, "
                     "due_date=COALESCE(due_date, ?), document_id=COALESCE(document_id, ?) WHERE id=?",
                     (ex.total, ex.gst, ex.total, due.isoformat() if due else None, doc_id, existing["id"]))
        raise_item(conn, "decision", f"Possible duplicate invoice {inv_no} from {ex.vendor_name}", "Same vendor and invoice number seen twice. Check before paying.",
                   "ap_invoices", existing["id"], priority=2)
        return f"invoice {inv_no} already on register (updated)"
    unit = equipment_unit(conn, ex)
    aid = db.insert(conn, "ap_invoices", dict(
        vendor_id=vid, invoice_no=inv_no, invoice_date=inv_date.isoformat() if inv_date else None, due_date=due.isoformat() if due else None,
        amount=ex.total, gst=ex.gst, amount_confirmed=1 if ex.total is not None else 0, status="Unpaid",
        planned_pay_date=due.isoformat() if due else None, job_no=job, cost_code=code if conf >= 0.5 else None, document_id=doc_id,
        category=(v["category"] if v else "supplier"), notes=((f"[{unit}] " if unit else "") + (ex.notes or desc or ""))[:500], created_at=db.now_iso()))
    if ex.total is None:
        raise_item(conn, "unconfirmed_amount", f"Invoice with no amount: {ex.vendor_name} {inv_no}", "Open the PDF or the supplier portal and enter the amount.",
                   "ap_invoices", aid, priority=2)
    if not due:
        raise_item(conn, "no_pay_date", f"Invoice with no due or pay date: {ex.vendor_name} {inv_no} ${ex.total or 0:,.2f}",
                   "An item with no planned pay date is invisible to the 13-week forecast. Set one.", "ap_invoices", aid, priority=2)
    return f"invoice {ex.vendor_name} {inv_no} ${ex.total} due {due}"


def _vendor_statement(conn, settings, doc_id, ex: Extraction, sender, subject) -> str:
    vid = vendors.find_or_create(conn, ex.vendor_name, sender)
    if not vid or ex.total is None:
        return "statement: no vendor or balance"
    open_ap = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM ap_invoices WHERE vendor_id=? AND status NOT IN ('Paid','Void-Credit','Reference only')", (vid,)).fetchone()["s"]
    diff = round(float(ex.total) - float(open_ap), 2)
    if abs(diff) >= 1.0:
        raise_item(conn, "decision", f"{ex.vendor_name} statement says ${ex.total:,.2f}; register says ${open_ap:,.2f}",
                   f"Difference ${diff:,.2f}. Either an invoice never arrived (ask them for it) or a payment has not been recorded.",
                   "vendors", vid, priority=2)
    return f"statement {ex.vendor_name} balance ${ex.total} vs register ${open_ap}"


def _customer_payment(conn, settings, doc_id, ex: Extraction, sender, subject) -> str:
    inv_nos = re.findall(r"\b(?:INV|Invoice)?\s*#?\s*(\d{3,6})\b", (ex.notes or "") + " " + (ex.invoice_no or ""), flags=re.I)
    marked = 0
    for n in inv_nos:
        cur = conn.execute("UPDATE ar_invoices SET status='Paid', paid_date=?, paid_amount=amount, document_id=COALESCE(document_id, ?) "
                           "WHERE invoice_no=? AND status IN ('Open','Partially Paid','Estimate')", (ex.doc_date, doc_id, n))
        marked += cur.rowcount
    if not marked and ex.total:
        r = conn.execute("SELECT id FROM ar_invoices WHERE status IN ('Open','Partially Paid','Estimate') AND ABS(amount - paid_amount - ?) < 0.005 "
                         "AND UPPER(customer) LIKE ?", (ex.total, f"%{(ex.customer_name or '')[:6].upper()}%")).fetchone()
        if r:
            conn.execute("UPDATE ar_invoices SET status='Paid', paid_date=?, paid_amount=amount, document_id=? WHERE id=?", (ex.doc_date, doc_id, r["id"]))
            marked = 1
    if not marked:
        raise_item(conn, "unmatched_deposit", f"Payment advice from {ex.customer_name or 'unknown'} ${ex.total or 0:,.2f} matches no open invoice",
                   f"Invoice numbers read: {inv_nos or 'none'}. Which invoice is this paying?", "documents", doc_id, priority=2)
    return f"customer payment {ex.customer_name} ${ex.total}: {marked} invoice(s) marked paid"


def _customer_invoice(conn, settings, doc_id, ex: Extraction, sender, subject) -> str:
    job = _norm_job(conn, ex.handwritten_job_no, f"{subject or ''} {ex.notes or ''} {ex.customer_name or ''}")
    due = parse_date(ex.due_date) or ((parse_date(ex.doc_date) + timedelta(days=30)) if parse_date(ex.doc_date) else None)
    hb = round(float(ex.total) * 0.10, 2) if ex.total and re.search(r"holdback", ex.notes or "", re.I) else 0.0
    db.upsert_ignore(conn, "ar_invoices", dict(
        customer=ex.customer_name or "Unknown", invoice_no=ex.invoice_no or f"DOC{doc_id}", invoice_date=ex.doc_date, due_date=due.isoformat() if due else None,
        amount=float(ex.total or 0), holdback=hb, status="Open", expected_date=due.isoformat() if due else None, job_no=job, document_id=doc_id,
        notes=(ex.notes or "")[:500], created_at=db.now_iso()))
    return f"AR invoice {ex.customer_name} {ex.invoice_no} ${ex.total}"


def _timesheet(conn, settings, doc_id, ex: Extraction, sender, subject) -> str:
    return ts.record_timesheet(conn, settings, doc_id, ex)


def _paystub(conn, settings, doc_id, ex: Extraction, sender, subject) -> str:
    pe = parse_date(ex.period_end)
    if not pe:
        return "paystub: no period end"
    r = conn.execute("SELECT id, net FROM payroll_runs WHERE period_end=?", (pe.isoformat(),)).fetchone()
    net = float(ex.total or 0)
    if r:
        conn.execute("UPDATE payroll_runs SET net=COALESCE(net,0)+?, status='submitted' WHERE id=?", (net, r["id"]))
    else:
        db.insert(conn, "payroll_runs", dict(period_end=pe.isoformat(), pay_date=(pe + timedelta(days=6)).isoformat(), net=net, status="submitted",
                                             notes=f"from paystub {ex.employee_name}"))
    return f"paystub {ex.employee_name} net ${net}"


def _bank_statement(conn, settings, doc_id, ex: Extraction, sender, subject) -> str:
    key = bank_import.account_key_for(settings, ex.account_hint)
    if not key:
        raise_item(conn, "decision", f"Bank statement could not be matched to an account ({ex.account_hint})", "Add the account to config or rename the hint.",
                   "documents", doc_id, priority=2)
        return "bank statement: unknown account"
    found, new = bank_import.import_extraction(conn, key, ex, statement_ref=f"doc:{doc_id}")
    return f"bank statement {key}: {new} new of {found} lines"


UNIT_RX = re.compile(r"\b([A-Z]{2,3}-\d{2,3})\b")


def equipment_unit(conn: sqlite3.Connection, ex: Extraction) -> str | None:
    """EX-03 written on the receipt, or on an invoice line, or a known unit named in the notes."""
    cands = [ex.handwritten_equipment_id] + [li.equipment_id for li in ex.line_items] + [ex.notes or ""] + [li.description for li in ex.line_items]
    for c in cands:
        if not c:
            continue
        m = UNIT_RX.search(str(c).upper().replace(" ", "-") if len(str(c)) <= 8 else str(c).upper())
        if m:
            return m.group(1)
    return None


def equipment_folder(conn: sqlite3.Connection, settings, unit_id: str) -> str:
    r = conn.execute("SELECT sharepoint_folder FROM equipment WHERE unit_id=?", (unit_id,)).fetchone()
    if r and r["sharepoint_folder"]:
        return r["sharepoint_folder"]
    folder = f"{settings.sharepoint.get('equipment', '05_EQUIPMENT/01_FLEET')}/{unit_id}"   # library 'resources' (equipment_site) unless configured otherwise
    conn.execute("INSERT INTO equipment(unit_id, sharepoint_folder) VALUES(?,?) ON CONFLICT(unit_id) DO UPDATE SET sharepoint_folder=COALESCE(equipment.sharepoint_folder, excluded.sharepoint_folder)", (unit_id, folder))
    conn.commit()
    return folder
