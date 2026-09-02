"""Cost by job and cost code: labour (loaded), receipts, vendor invoices. Compare to the estimate when one is loaded."""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from .. import db
from . import timesheets


def job_cost(conn: sqlite3.Connection, settings, start: str | None = None, end: str | None = None) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(lambda: dict(labour=0.0, labour_hours=0.0, receipts=0.0, invoices=0.0, by_code=defaultdict(float)))
    for r in timesheets.labour_cost_by_job(conn, settings, start, end):
        j = r["job_no"] or "UNASSIGNED"
        out[j]["labour"] += r["cost"]
        out[j]["labour_hours"] += r["hours"] + r["ot_hours"]
        out[j]["by_code"][r["cost_code"] or "UNCODED"] += r["cost"]
    q = "SELECT job_no, cost_code, COALESCE(amount,0) - COALESCE(gst,0) AS net FROM receipts WHERE 1=1"
    p: list = []
    if start:
        q += " AND receipt_date>=?"; p.append(start)
    if end:
        q += " AND receipt_date<=?"; p.append(end)
    for r in db.rows(conn, q, p):
        j = r["job_no"] or "UNASSIGNED"
        out[j]["receipts"] += r["net"]
        out[j]["by_code"][r["cost_code"] or "UNCODED"] += r["net"]
    q = "SELECT job_no, cost_code, COALESCE(amount,0) - COALESCE(gst,0) AS net FROM ap_invoices WHERE status NOT IN ('Void-Credit','Reference only')"
    p = []
    if start:
        q += " AND invoice_date>=?"; p.append(start)
    if end:
        q += " AND invoice_date<=?"; p.append(end)
    for r in db.rows(conn, q, p):
        j = r["job_no"] or "UNASSIGNED"
        out[j]["invoices"] += r["net"]
        out[j]["by_code"][r["cost_code"] or "UNCODED"] += r["net"]
    for j, v in out.items():
        v["total"] = round(v["labour"] + v["receipts"] + v["invoices"], 2)
        v["by_code"] = dict(v["by_code"])
        jr = conn.execute("SELECT name, client, contract_value FROM jobs WHERE job_no=?", (j,)).fetchone()
        v["name"] = jr["name"] if jr else ("Unassigned" if j == "UNASSIGNED" else j)
        v["contract_value"] = jr["contract_value"] if jr else None
        billed = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM ar_invoices WHERE job_no=? AND status<>'Estimate'", (j,)).fetchone()["s"]
        v["billed"] = round(float(billed), 2)
        v["margin_to_date"] = round(v["billed"] - v["total"], 2)
    return dict(out)
