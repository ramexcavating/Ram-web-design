"""Vendor identity. The same supplier arrives as 'Four Rivers Co-op', 'FOUR RIVERS CO-OPERATIVE', 'fourrivers.coop'."""
from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

from .filing import slug


def norm(name: str | None) -> str:
    return slug(name, 40)


def load_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    n = 0
    with open(p, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            name = (r.get("name") or "").strip()
            if not name:
                continue
            conn.execute(
                "INSERT INTO vendors(name, norm_name, aliases, email_domain, default_cost_code, default_terms_days, category, critical, default_job) "
                "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(norm_name) DO UPDATE SET aliases=excluded.aliases, email_domain=excluded.email_domain, "
                "default_cost_code=excluded.default_cost_code, default_terms_days=excluded.default_terms_days, category=excluded.category, critical=excluded.critical, default_job=excluded.default_job",
                (name, norm(name), r.get("aliases") or "", (r.get("email_domain") or "").lower() or None, r.get("default_cost_code") or None,
                 int(r.get("default_terms_days") or 30), r.get("category") or "supplier", 1 if str(r.get("critical", "0")).strip() in ("1", "yes", "true", "Y") else 0,
                 (r.get("default_job") or "").strip() or None),
            )
            n += 1
    conn.commit()
    return n


def find_or_create(conn: sqlite3.Connection, name: str | None, sender_email: str | None = None) -> int | None:
    if not name and not sender_email:
        return None
    if name:
        n = norm(name)
        row = conn.execute("SELECT id FROM vendors WHERE norm_name=?", (n,)).fetchone()
        if row:
            return row["id"]
        for v in conn.execute("SELECT id, aliases FROM vendors WHERE aliases<>''"):
            if n in [norm(a) for a in v["aliases"].split("|") if a.strip()]:
                return v["id"]
    if sender_email and "@" in sender_email:
        dom = sender_email.split("@", 1)[1].lower()
        row = conn.execute("SELECT id FROM vendors WHERE email_domain=?", (dom,)).fetchone()
        if row:
            return row["id"]
    if not name:
        return None
    cur = conn.execute("INSERT INTO vendors(name, norm_name, email_domain) VALUES(?,?,?)",
                       (name.strip(), norm(name), sender_email.split("@", 1)[1].lower() if sender_email and "@" in sender_email else None))
    return int(cur.lastrowid)


def is_critical(conn: sqlite3.Connection, vendor_id: int | None) -> bool:
    if not vendor_id:
        return False
    r = conn.execute("SELECT critical, category FROM vendors WHERE id=?", (vendor_id,)).fetchone()
    return bool(r and (r["critical"] or r["category"] in ("payroll", "cra", "debt")))


def is_personal(conn: sqlite3.Connection, vendor_id: int | None) -> bool:
    if not vendor_id:
        return False
    r = conn.execute("SELECT category FROM vendors WHERE id=?", (vendor_id,)).fetchone()
    return bool(r and r["category"] == "personal")


def default_job(conn: sqlite3.Connection, vendor_id: int | None) -> str | None:
    if not vendor_id:
        return None
    r = conn.execute("SELECT default_job FROM vendors WHERE id=?", (vendor_id,)).fetchone()
    return r["default_job"] if r and r["default_job"] else None
