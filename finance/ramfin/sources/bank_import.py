"""Bank data in. Two routes:
  1. CSV exports from online banking (RBC, TD, Capital One) - exact, preferred, takes 2 minutes a month.
  2. PDF statements extracted by Claude (bank_statement doc_type) - fallback when only the PDF exists.
Both land in bank_transactions with the same de-duplication key."""
from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime

from .. import db
from ..models import Extraction
from ..rules.filing import parse_date


def _amt(s: str | None) -> float:
    if s is None:
        return 0.0
    s = str(s).replace("$", "").replace(",", "").strip()
    if not s:
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


def parse_rbc_csv(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        d = parse_date(r.get("Transaction Date"))
        if not d:
            continue
        desc = " ".join(x for x in [r.get("Description 1", ""), r.get("Description 2", "")] if x).strip()
        amt = _amt(r.get("CAD$")) or _amt(r.get("USD$"))
        out.append(dict(txn_date=d.isoformat(), description=desc or (r.get("Cheque Number") and f"CHQ {r['Cheque Number']}") or "RBC", amount=amt, balance=None))
    return out


def parse_td_csv(text: str) -> list[dict]:
    """TD exports have no header: date, description, debit, credit, balance."""
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 4:
            continue
        d = parse_date(row[0])
        if not d:
            continue
        debit, credit = _amt(row[2]), _amt(row[3])
        bal = _amt(row[4]) if len(row) > 4 and row[4].strip() else None
        out.append(dict(txn_date=d.isoformat(), description=row[1].strip(), amount=credit - debit, balance=bal))
    return out


def parse_capitalone_csv(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        d = parse_date(r.get("Transaction Date") or r.get("Posted Date"))
        if not d:
            continue
        debit, credit = _amt(r.get("Debit")), _amt(r.get("Credit"))
        out.append(dict(txn_date=d.isoformat(), description=(r.get("Description") or "").strip(), amount=credit - debit, balance=None))
    return out


def parse_generic_csv(text: str) -> list[dict]:
    """Header row with date/description/amount (or debit+credit) columns, any case."""
    out = []
    rd = csv.DictReader(io.StringIO(text))
    cols = {c.lower().strip(): c for c in rd.fieldnames or []}
    dcol = next((cols[c] for c in cols if "date" in c), None)
    desc = next((cols[c] for c in cols if "desc" in c or "memo" in c or "payee" in c), None)
    amt = next((cols[c] for c in cols if c in ("amount", "amt")), None)
    debit = next((cols[c] for c in cols if "debit" in c or "withdraw" in c), None)
    credit = next((cols[c] for c in cols if "credit" in c or "deposit" in c), None)
    bal = next((cols[c] for c in cols if "balance" in c), None)
    for r in rd:
        d = parse_date(r.get(dcol)) if dcol else None
        if not d:
            continue
        a = _amt(r.get(amt)) if amt else _amt(r.get(credit)) - _amt(r.get(debit))
        out.append(dict(txn_date=d.isoformat(), description=(r.get(desc) or "").strip() if desc else "", amount=a,
                        balance=_amt(r.get(bal)) if bal and r.get(bal) else None))
    return out


PARSERS = {"rbc_csv": parse_rbc_csv, "td_csv": parse_td_csv, "capitalone_csv": parse_capitalone_csv, "generic_csv": parse_generic_csv}


def store_lines(conn: sqlite3.Connection, account_key: str, lines: list[dict], statement_ref: str | None = None) -> tuple[int, int]:
    found = new = 0
    seen: dict[tuple, int] = {}
    for ln in lines:
        found += 1
        k = (ln["txn_date"], ln["description"], round(float(ln["amount"]), 2))
        seq = seen.get(k, 0)
        seen[k] = seq + 1
        row = dict(account_key=account_key, txn_date=ln["txn_date"], description=ln["description"], amount=round(float(ln["amount"]), 2),
                   balance=ln.get("balance"), seq=seq, statement_ref=statement_ref, created_at=db.now_iso())
        if db.upsert_ignore(conn, "bank_transactions", row):
            new += 1
    conn.commit()
    return found, new


def import_csv(conn: sqlite3.Connection, account_key: str, fmt: str, text: str, statement_ref: str | None = None) -> tuple[int, int]:
    parser = PARSERS.get(fmt, parse_generic_csv)
    lines = parser(text)
    found, new = store_lines(conn, account_key, lines, statement_ref)
    latest = max(lines, key=lambda x: x["txn_date"], default=None)
    if latest and latest.get("balance") is not None:
        db.upsert_ignore(conn, "bank_balances", dict(as_of=latest["txn_date"], account_key=account_key, balance=latest["balance"],
                                                     source="csv", created_at=db.now_iso()))
        conn.commit()
    db.log_scan(conn, "bank_import", f"{account_key}:{fmt}", found, new, 0)
    return found, new


def import_extraction(conn: sqlite3.Connection, account_key: str, ex: Extraction, statement_ref: str | None = None) -> tuple[int, int]:
    lines = [dict(txn_date=(parse_date(b.txn_date) or datetime.today().date()).isoformat(), description=b.description, amount=b.amount, balance=b.balance)
             for b in ex.bank_lines]
    found, new = store_lines(conn, account_key, lines, statement_ref)
    if ex.closing_balance is not None and ex.statement_end:
        end = parse_date(ex.statement_end)
        if end:
            db.upsert_ignore(conn, "bank_balances", dict(as_of=end.isoformat(), account_key=account_key, balance=ex.closing_balance,
                                                         source="statement", created_at=db.now_iso()))
            conn.commit()
    return found, new


def account_key_for(settings, hint: str | None) -> str | None:
    """Map 'TD Business Visa ****4321' style hints to a configured account key."""
    if not hint:
        return None
    h = hint.lower()
    for a in settings.bank_accounts:
        inst = a.institution.lower()
        if inst and inst in h:
            if a.kind == "card" and ("visa" in h or "mastercard" in h or "card" in h):
                return a.key
            if a.kind == "chequing" and ("chequing" in h or "checking" in h or "business" in h) and "visa" not in h:
                return a.key
            if a.kind == "loc" and ("line" in h or "loc" in h):
                return a.key
    for a in settings.bank_accounts:
        if a.institution.lower() in h:
            return a.key
    return None
