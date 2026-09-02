"""Bank line categorisation and matching. Every purchase on a statement should have a receipt, an invoice, or a rule
that says one is not required (fees, transfers, CRA, loan payments). Whatever is left is the list to chase."""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta

from .. import db
from .filing import parse_date

RULES = [
    # (regex, category, receipt_required)
    (r"\b(service charge|monthly fee|account fee|nsf|overdraft|interest charge|fee)\b", "fee", 0),
    (r"\binterest\b", "interest", 0),
    (r"\b(transfer|tfr|e-?transfer|internet transfer|wire)\b", "transfer", 0),
    (r"\b(payment - thank you|pymt|credit card payment|visa payment|mastercard payment|capital one)\b", "card_payment", 0),
    (r"\b(loan|lease|lending loop|ceba|cwb|community futures|mortgage|financing)\b", "loan", 0),
    (r"\b(cra|receiver general|revenue canada|gst|pst|worksafe|wcb)\b", "cra", 0),
    (r"\b(payroll|acg|pay run|direct deposit - payroll)\b", "payroll", 0),
    (r"\b(insurance|cansure|lloyd)\b", "insurance", 0),
    (r"\b(deposit|eft credit|incoming|remittance)\b", "deposit", 0),
]
SMALL_PURCHASE_FLOOR = 10.0   # below this a missing receipt is not worth an action item; still shows in the export


def categorise(description: str, amount: float) -> tuple[str, int]:
    d = (description or "").lower()
    for rx, cat, req in RULES:
        if re.search(rx, d):
            if cat == "deposit" and amount < 0:
                continue
            return cat, req
    if amount > 0:
        return "deposit", 0
    return "purchase", 1


def _match_receipt(conn: sqlite3.Connection, txn) -> int | None:
    d = parse_date(txn["txn_date"])
    amt = round(-float(txn["amount"]), 2)
    lo, hi = (d - timedelta(days=7)).isoformat(), (d + timedelta(days=7)).isoformat()
    r = conn.execute("SELECT id FROM receipts WHERE matched_txn_id IS NULL AND ABS(amount - ?) < 0.005 AND receipt_date BETWEEN ? AND ? "
                     "ORDER BY ABS(julianday(receipt_date) - julianday(?)) LIMIT 1", (amt, lo, hi, d.isoformat())).fetchone()
    return r["id"] if r else None


def _match_ap(conn: sqlite3.Connection, txn) -> int | None:
    d = parse_date(txn["txn_date"])
    amt = round(-float(txn["amount"]), 2)
    lo, hi = (d - timedelta(days=45)).isoformat(), (d + timedelta(days=5)).isoformat()
    desc = (txn["description"] or "").upper()
    rows = db.rows(conn, "SELECT a.id, v.norm_name FROM ap_invoices a LEFT JOIN vendors v ON v.id=a.vendor_id "
                         "WHERE a.status<>'Paid' AND ABS(a.amount - ?) < 0.005 AND COALESCE(a.invoice_date, a.created_at) BETWEEN ? AND ?", (amt, lo, hi))
    if len(rows) == 1:
        return rows[0]["id"]
    for r in rows:
        if r["norm_name"] and r["norm_name"][:6] in re.sub(r"[^A-Z0-9]", "", desc):
            return r["id"]
    return None


def _match_ar(conn: sqlite3.Connection, txn) -> int | None:
    amt = round(float(txn["amount"]), 2)
    d = parse_date(txn["txn_date"])
    rows = db.rows(conn, "SELECT id FROM ar_invoices WHERE status IN ('Open','Partially Paid') AND ABS((amount - paid_amount) - ?) < 0.005", (amt,))
    if len(rows) == 1:
        return rows[0]["id"]
    # a customer paying several invoices in one EFT
    opens = db.rows(conn, "SELECT id, customer, amount - paid_amount AS bal FROM ar_invoices WHERE status IN ('Open','Partially Paid') ORDER BY customer, invoice_date")
    by_cust: dict[str, list] = {}
    for r in opens:
        by_cust.setdefault(r["customer"], []).append(r)
    for cust, items in by_cust.items():
        if abs(sum(i["bal"] for i in items) - amt) < 0.005 and len(items) > 1:
            return items[0]["id"]  # caller marks the whole customer set paid
    return None


def match_transactions(conn: sqlite3.Connection, since: str | None = None) -> dict[str, int]:
    from ..notify.inbox import raise_item
    stats = {"scanned": 0, "receipt": 0, "ap": 0, "ar": 0, "rule": 0, "missing": 0}
    q = "SELECT * FROM bank_transactions WHERE match_type IS NULL OR match_type='none'"
    params: tuple = ()
    if since:
        q += " AND txn_date >= ?"
        params = (since,)
    for txn in db.rows(conn, q + " ORDER BY txn_date", params):
        stats["scanned"] += 1
        cat, req = categorise(txn["description"], txn["amount"])
        match_type, match_id = "none", None
        if txn["amount"] < 0:
            rid = _match_receipt(conn, txn)
            if rid:
                match_type, match_id = "receipt", rid
                conn.execute("UPDATE receipts SET matched_txn_id=? WHERE id=?", (txn["id"], rid))
                stats["receipt"] += 1
            else:
                aid = _match_ap(conn, txn)
                if aid:
                    match_type, match_id = "ap", aid
                    conn.execute("UPDATE ap_invoices SET status='Paid', paid_date=?, method='bank' WHERE id=? AND status<>'Paid'", (txn["txn_date"], aid))
                    stats["ap"] += 1
        else:
            arid = _match_ar(conn, txn)
            if arid:
                match_type, match_id = "ar", arid
                cust = conn.execute("SELECT customer FROM ar_invoices WHERE id=?", (arid,)).fetchone()["customer"]
                bal = conn.execute("SELECT amount - paid_amount b FROM ar_invoices WHERE id=?", (arid,)).fetchone()["b"]
                if abs(bal - txn["amount"]) < 0.005:
                    conn.execute("UPDATE ar_invoices SET status='Paid', paid_date=?, paid_amount=amount WHERE id=?", (txn["txn_date"], arid))
                else:
                    conn.execute("UPDATE ar_invoices SET status='Paid', paid_date=?, paid_amount=amount WHERE customer=? AND status IN ('Open','Partially Paid')",
                                 (txn["txn_date"], cust))
                stats["ar"] += 1
        if match_type == "none" and not req:
            match_type = "rule"
            stats["rule"] += 1
        conn.execute("UPDATE bank_transactions SET category=?, receipt_required=?, match_type=?, match_id=? WHERE id=?",
                     (cat, req, match_type, match_id, txn["id"]))
        if match_type == "none" and txn["amount"] < 0 and req and -txn["amount"] >= SMALL_PURCHASE_FLOOR:
            stats["missing"] += 1
            raise_item(conn, "missing_receipt", f"Missing receipt: {txn['description'][:50]} ${-txn['amount']:,.2f} on {txn['txn_date']}",
                       "Business purchase on a statement with no receipt or invoice behind it. Photograph it to accounts@ with RECEIPT in the subject, or mark the line as personal.",
                       "bank_transactions", txn["id"], priority=3)
        if match_type == "none" and txn["amount"] > 0 and cat in ("deposit",) and txn["amount"] >= 500:
            raise_item(conn, "unmatched_deposit", f"Unmatched deposit ${txn['amount']:,.2f} on {txn['txn_date']}: {txn['description'][:50]}",
                       "Money arrived that does not match an open receivable. Which invoice or job is this?", "bank_transactions", txn["id"], priority=2)
    conn.commit()
    return stats


def capture_rate(conn: sqlite3.Connection, since: str | None = None) -> tuple[int, int]:
    """(purchases with something behind them, purchases requiring a receipt)"""
    q = "SELECT COUNT(*) n, SUM(CASE WHEN match_type IN ('receipt','ap') THEN 1 ELSE 0 END) m FROM bank_transactions WHERE receipt_required=1 AND amount<0"
    p: tuple = ()
    if since:
        q += " AND txn_date>=?"
        p = (since,)
    r = conn.execute(q, p).fetchone()
    return int(r["m"] or 0), int(r["n"] or 0)
