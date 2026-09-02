"""Cost codes and the vendor -> cost code memory.

The 825-code RAM standard list lives in SharePoint (03_AP/5.1.08 Budget & Cost Codes) and in the COST_CODES tab of the
AP register. Export it once to config/cost_codes.csv (code,description,category). The system then learns: every time
a receipt or invoice is coded (by hand on the receipt, or by Rodney in the review sheet), the vendor's most common
code becomes the default suggestion next time.
"""
from __future__ import annotations

import csv
import re
import sqlite3
from collections import Counter
from pathlib import Path

from .. import db

KEYWORD_HINTS = [
    # (regex on vendor/description, RAM standard cost code, label)
    (r"fuel|diesel|cardlock|petro|shell|esso|husky|co-?op|four rivers", "1-294", "Fuel for Equipment"),
    (r"brandt|wajax|finning|inland|kubota|bumper ?to ?bumper|uni-?select|lordco|napa|parts|hydraulic|tire|royalite|repair", "1-296", "Equipment Repairs"),
    (r"home hardware|rona|canadian tire|princess auto|tenaquip|white cap|small tools", "1-293", "Small Tools"),
    (r"gravel|aggregate|pit run|crush|united concrete", "2-108", "Bulk Backfill Import"),
    (r"concrete|precast|grosso|lekop|konkast|curb", "2-186", "Concrete Curb and Gutter"),
    (r"rent-?all|rental|united rentals|herc", "1-298", "Rental Equipment"),
    (r"insurance|cansure|lloyd|acera", "1-180", "General Liability Insurance"),
    (r"hydro|fortis|telus|shaw|xplore|rogers|bell", "50-212", "Site Office and utilities"),
    (r"quickbooks|intuit|godaddy|microsoft|anthropic|adobe|camscanner|equifax|apple", "50-271", "Office Supplies and software"),
    (r"google ads|wordpress|advertis|sign", "1-312", "Publications & Advertising"),
    (r"acg|accounting|tbj|cpa", "50-063", "Administration"),
    (r"legal|lawyer", "1-184", "Legal Costs"),
    (r"worksafe|wcb|cra|receiver general", "1-170", "WSBC Claims Management"),
    (r"survey|cansel|lease direct", "1-080", "Survey"),
    (r"mobe|mobiliz|lowbed|float", "1-042", "Equipment Mobe/Demobe"),
]

FUEL_CODES = {"1-292", "1-294", "1-297", "50-292", "50-912"}
REPAIR_CODES = {"1-295", "1-296", "1-313", "1-314"}


def load_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    n = 0
    with open(p, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            code = (r.get("code") or "").strip()
            if not code:
                continue
            conn.execute(
                "INSERT INTO cost_codes(code, description, category) VALUES(?,?,?) "
                "ON CONFLICT(code) DO UPDATE SET description=excluded.description, category=excluded.category",
                (code, (r.get("description") or "").strip(), (r.get("category") or "").strip() or None),
            )
            n += 1
    conn.commit()
    return n


def is_valid(conn: sqlite3.Connection, code: str | None) -> bool:
    if not code:
        return False
    return conn.execute("SELECT 1 FROM cost_codes WHERE code=?", (code.strip(),)).fetchone() is not None


def normalise_handwritten(code: str | None) -> str | None:
    """Handwriting comes back as '02-300', '02.300', '2300', ' 02 300 '. Reduce to digits-and-dashes upper-case."""
    if not code:
        return None
    c = re.sub(r"[^0-9A-Za-z-]", "", str(code).replace(".", "-").replace(" ", "-")).upper()
    return c or None


def vendor_history(conn: sqlite3.Connection, vendor_id: int | None) -> Counter:
    if not vendor_id:
        return Counter()
    c: Counter = Counter()
    for r in db.rows(conn, "SELECT cost_code FROM receipts WHERE vendor_id=? AND cost_code IS NOT NULL", (vendor_id,)):
        c[r["cost_code"]] += 1
    for r in db.rows(conn, "SELECT cost_code FROM ap_invoices WHERE vendor_id=? AND cost_code IS NOT NULL", (vendor_id,)):
        c[r["cost_code"]] += 1
    return c


def suggest(conn: sqlite3.Connection, vendor_id: int | None, vendor_name: str | None, description: str | None,
            handwritten: str | None = None) -> tuple[str | None, float, str]:
    """Return (code, confidence, why). A handwritten code that exists in the list always wins."""
    hw = normalise_handwritten(handwritten)
    if hw and is_valid(conn, hw):
        return hw, 0.98, "written on document"
    hist = vendor_history(conn, vendor_id)
    if hist:
        code, n = hist.most_common(1)[0]
        share = n / sum(hist.values())
        return code, min(0.9, 0.5 + share * 0.4), f"vendor history ({n} of {sum(hist.values())})"
    row = conn.execute("SELECT default_cost_code FROM vendors WHERE id=?", (vendor_id,)).fetchone() if vendor_id else None
    if row and row["default_cost_code"]:
        return row["default_cost_code"], 0.7, "vendor default"
    text = f"{vendor_name or ''} {description or ''}".lower()
    for rx, code, label in KEYWORD_HINTS:
        if re.search(rx, text) and is_valid(conn, code):
            return code, 0.4, f"keyword hint {label}"
    if hw:
        return hw, 0.3, "written on document but not in the standard list"
    return None, 0.0, "no suggestion"
