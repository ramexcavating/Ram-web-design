"""Timesheets -> digital time entries -> labour cost by job and cost code -> payroll accrual."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .. import db
from ..models import Extraction
from ..notify.inbox import raise_item
from ..rules.filing import parse_date

MAX_HOURS_DAY = 14.0


def employee_id(conn: sqlite3.Connection, name: str | None, position: str | None = None) -> int | None:
    if not name:
        return None
    n = " ".join(name.split()).title()
    r = conn.execute("SELECT id FROM employees WHERE UPPER(name)=UPPER(?)", (n,)).fetchone()
    if r:
        return r["id"]
    parts = n.split()
    if parts:
        r = conn.execute("SELECT id FROM employees WHERE UPPER(name) LIKE ?", (f"%{parts[-1].upper()}%",)).fetchone()
        if r and len(parts) > 1:
            first = conn.execute("SELECT name FROM employees WHERE id=?", (r["id"],)).fetchone()["name"]
            if first.split()[0][0].upper() == parts[0][0].upper():
                return r["id"]
    return db.insert(conn, "employees", dict(name=n, position=position, active=1))


def record_timesheet(conn: sqlite3.Connection, settings, doc_id: int, ex: Extraction) -> str:
    eid = employee_id(conn, ex.employee_name)
    pe = parse_date(ex.period_end)
    if not pe and ex.time_entries:
        pe = max(parse_date(t.work_date) or date.min for t in ex.time_entries)
    if not eid or not pe:
        raise_item(conn, "timesheet_issue", f"Timesheet missing employee or period end (doc {doc_id})", "Could not read who or when. Check the scan.",
                   "documents", doc_id, priority=2)
        return "timesheet: unreadable header"
    existing = conn.execute("SELECT id FROM timesheets WHERE employee_id=? AND period_end=?", (eid, pe.isoformat())).fetchone()
    if existing:
        tsid = existing["id"]
        conn.execute("DELETE FROM time_entries WHERE timesheet_id=?", (tsid,))
        conn.execute("UPDATE timesheets SET document_id=? WHERE id=?", (doc_id, tsid))
    else:
        tsid = db.insert(conn, "timesheets", dict(employee_id=eid, period_end=pe.isoformat(), document_id=doc_id, status="received", created_at=db.now_iso()))
    total = ot = 0.0
    issues = []
    from .intake import _norm_job  # local import to avoid a cycle at module load
    header_job = _norm_job(conn, ex.handwritten_job_no, ex.notes or "")   # the sheet's own job box, when filled in
    for t in ex.time_entries:
        d = parse_date(t.work_date)
        if not d:
            issues.append(f"unreadable date {t.work_date!r}")
            continue
        job = _norm_job(conn, t.job_no, t.description or "") or header_job
        if not job and (t.hours or t.ot_hours):
            issues.append(f"{d}: {t.hours}h with no job ({t.job_no or t.description or 'blank'}). LOA, travel and shop time are coded to the job worked, not to overhead.")
        if (t.hours or 0) + (t.ot_hours or 0) > MAX_HOURS_DAY:
            issues.append(f"{d}: {t.hours + t.ot_hours}h in one day")
        db.insert(conn, "time_entries", dict(timesheet_id=tsid, work_date=d.isoformat(), job_no=job, cost_code=t.cost_code, hours=float(t.hours or 0),
                                             ot_hours=float(t.ot_hours or 0), equipment_id=t.equipment_id, description=t.description))
        total += float(t.hours or 0)
        ot += float(t.ot_hours or 0)
    conn.execute("UPDATE timesheets SET total_hours=?, total_ot_hours=?, status=? WHERE id=?", (total, ot, "validated" if not issues else "received", tsid))
    if issues:
        raise_item(conn, "timesheet_issue", f"Timesheet {ex.employee_name} PP {pe}: {len(issues)} issue(s)", "\n".join(issues), "timesheets", tsid, priority=2)
    ensure_payroll_run(conn, settings, pe)
    conn.commit()
    return f"timesheet {ex.employee_name} PP {pe}: {total}h + {ot}h OT, {len(issues)} issue(s)"


def ensure_payroll_run(conn: sqlite3.Connection, settings, period_end: date) -> None:
    if conn.execute("SELECT 1 FROM payroll_runs WHERE period_end=?", (period_end.isoformat(),)).fetchone():
        return
    pay = period_end + timedelta(days=(4 - period_end.weekday()) % 7 or 7)   # following Friday
    db.insert(conn, "payroll_runs", dict(period_end=period_end.isoformat(), pay_date=pay.isoformat(), status="projected"))


def loaded_rate(conn: sqlite3.Connection, settings, employee_id: int) -> float:
    r = conn.execute("SELECT base_rate FROM employees WHERE id=?", (employee_id,)).fetchone()
    base = float(r["base_rate"] or 0) if r else 0.0
    return round(base * settings.labour_burden, 2)


def labour_cost_by_job(conn: sqlite3.Connection, settings, start: str | None = None, end: str | None = None) -> list[dict]:
    q = ("SELECT te.job_no, te.cost_code, ts.employee_id, e.name, SUM(te.hours) h, SUM(te.ot_hours) ot FROM time_entries te "
         "JOIN timesheets ts ON ts.id=te.timesheet_id JOIN employees e ON e.id=ts.employee_id WHERE 1=1")
    p: list = []
    if start:
        q += " AND te.work_date>=?"; p.append(start)
    if end:
        q += " AND te.work_date<=?"; p.append(end)
    q += " GROUP BY te.job_no, te.cost_code, ts.employee_id"
    out = []
    for r in db.rows(conn, q, p):
        rate = loaded_rate(conn, settings, r["employee_id"])
        out.append(dict(job_no=r["job_no"], cost_code=r["cost_code"], employee=r["name"], hours=r["h"], ot_hours=r["ot"],
                        cost=round(r["h"] * rate + r["ot"] * rate * 1.5, 2), rate=rate))
    return out


def payroll_accrual(conn: sqlite3.Connection, settings, period_end: str) -> dict:
    rows = db.rows(conn, "SELECT ts.employee_id, ts.total_hours, ts.total_ot_hours, e.base_rate FROM timesheets ts JOIN employees e ON e.id=ts.employee_id WHERE ts.period_end=?", (period_end,))
    gross = sum((r["total_hours"] or 0) * (r["base_rate"] or 0) + (r["total_ot_hours"] or 0) * (r["base_rate"] or 0) * 1.5 for r in rows)
    loaded = gross * settings.labour_burden
    return dict(period_end=period_end, employees=len(rows), gross=round(gross, 2), loaded=round(loaded, 2),
                missing_rates=[r["employee_id"] for r in rows if not r["base_rate"]])
