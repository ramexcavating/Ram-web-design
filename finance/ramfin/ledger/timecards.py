"""Digital timecards from the phone app (timecards/app) -> timesheets, time_entries, timecard_days.

A card is plain text ending in a machine block:

    --RAMTC1--
    {"v":1,"employee":"Ed Smith","periodEnd":"2026-09-12","days":[{"date":"2026-09-03","loa":true,"pu":false,"km":0,
     "lines":[{"job":"260805","cc":"2-200","reg":8,"ot":1,"dt":0,"unit":"EX-03","eq":9,"desc":"..."}]}]}
    --END--

No Claude call: the block is parsed here, deterministically. A re-sent day replaces only that day. Anything the card
says that the database does not know (job, cost code, unit, employee) becomes an action item, never a silent drop.
"""
from __future__ import annotations

import html
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .. import db
from ..notify.inbox import raise_item
from ..rules.filing import FilingDecision, parse_date, slug
from .timesheets import MAX_HOURS_DAY, ensure_payroll_run

SUBJECT_RX = re.compile(r"^\s*(re:|fwd?:)?\s*RAM Timecard\b", re.I)
BLOCK_RX = re.compile(r"--RAMTC1--\s*(\{.*?\})\s*--END--", re.S)
MARKER = b"--RAMTC1--"

# what the phone shows first in the cost code picker; everything else is searchable
DEFAULT_ALLOWANCES = {"loa": 220.0, "pickup": 150.0, "travel_km": 0.73}     # the rates printed on the paper weekly timesheet

FAVOURITE_CODES = ["2-100", "2-101", "2-102", "2-106", "2-107", "2-108", "2-111", "2-114", "2-200", "2-201", "2-202", "2-204", "2-205", "2-206",
                   "2-215", "2-217", "2-219", "2-226", "2-240", "2-261", "1-041", "1-042", "1-062", "1-067", "1-293", "1-294", "1-295", "1-296",
                   "50-120", "50-121", "50-160", "50-932", "70-001"]


def is_timecard(data: bytes, filename: str | None = None, subject: str | None = None) -> bool:
    if subject and SUBJECT_RX.search(subject):
        return True
    if filename and filename.lower().endswith(".ramtc.txt"):
        return True
    return MARKER in data[:200_000]


def _html_to_text(s: str) -> str:
    if "<" not in s or ">" not in s:
        return s
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


def parse(text: str | bytes) -> dict:
    """Return the card payload. Raises ValueError when there is no readable block."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = _html_to_text(text).replace("\xa0", " ")
    m = BLOCK_RX.search(text)
    if not m:
        raise ValueError("no --RAMTC1-- block in the message")
    raw = m.group(1)
    for fix in (lambda s: s, lambda s: re.sub(r"[\r\n]+", "", s), lambda s: re.sub(r"[\r\n]+", " ", s), lambda s: re.sub(r"=\r?\n", "", s)):
        try:
            payload = json.loads(fix(raw))
            break
        except json.JSONDecodeError:
            continue
    else:
        raise ValueError("timecard block is not valid JSON (mail client mangled it?)")
    if not isinstance(payload, dict) or payload.get("v") != 1 or not payload.get("employee") or not isinstance(payload.get("days"), list):
        raise ValueError("timecard block is missing employee or days")
    return payload


def _f(v) -> float:
    try:
        return max(0.0, float(v or 0))
    except (TypeError, ValueError):
        return 0.0


def _period_end(payload: dict) -> date | None:
    pe = parse_date(payload.get("periodEnd"))
    if pe:
        return pe
    ds = [parse_date(d.get("date")) for d in payload.get("days", [])]
    ds = [d for d in ds if d]
    return max(ds) if ds else None


def record_timecard(conn: sqlite3.Connection, settings, doc_id: int | None, payload: dict) -> str:
    from .timesheets import employee_id   # local import: timesheets imports nothing from here, but keep the graph one-way
    name = " ".join(str(payload["employee"]).split())
    known = conn.execute("SELECT id FROM employees WHERE UPPER(name)=UPPER(?)", (name,)).fetchone() is not None
    eid = employee_id(conn, name, payload.get("position"))
    pe = _period_end(payload)
    if not eid or not pe:
        raise_item(conn, "timesheet_issue", f"Timecard from {name!r} has no readable pay period", "The card came in but the dates could not be read.", "documents", doc_id, priority=2)
        return "timecard: unreadable"
    if not known:
        raise_item(conn, "timesheet_issue", f"New employee on a timecard: {name}", f"{name} sent a timecard but is not in the employee list. Confirm the name and add a base rate (employees table / config.yaml).",
                   "employees", eid, priority=2)
    ts = conn.execute("SELECT id FROM timesheets WHERE employee_id=? AND period_end=?", (eid, pe.isoformat())).fetchone()
    if ts:
        tsid = ts["id"]
        if doc_id:
            conn.execute("UPDATE timesheets SET document_id=? WHERE id=?", (doc_id, tsid))
    else:
        tsid = db.insert(conn, "timesheets", dict(employee_id=eid, period_end=pe.isoformat(), document_id=doc_id, status="received", created_at=db.now_iso()))

    have_equipment_table = conn.execute("SELECT COUNT(*) n FROM equipment").fetchone()["n"] > 0
    issues: list[str] = []
    days_done = 0
    lines_done = 0
    sent_at = payload.get("sentAt") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    for day in payload.get("days", []):
        d = parse_date(day.get("date"))
        if not d:
            issues.append(f"unreadable date {day.get('date')!r}")
            continue
        if not (pe.toordinal() - 13 <= d.toordinal() <= pe.toordinal()):
            issues.append(f"{d}: outside pay period ending {pe}")
        # replace this day only
        conn.execute("DELETE FROM time_entries WHERE timesheet_id=? AND work_date=?", (tsid, d.isoformat()))
        conn.execute("DELETE FROM timecard_days WHERE timesheet_id=? AND work_date=?", (tsid, d.isoformat()))
        day_hours = 0.0
        for ln in day.get("lines", []) or []:
            job = str(ln.get("job") or "").strip() or None
            cc = str(ln.get("cc") or "").strip() or None
            unit = str(ln.get("unit") or "").strip().upper() or None
            reg, ot, dt, eq = _f(ln.get("reg")), _f(ln.get("ot")), _f(ln.get("dt")), _f(ln.get("eq")) if unit else 0.0
            if job and not conn.execute("SELECT 1 FROM jobs WHERE job_no=?", (job,)).fetchone():
                issues.append(f"{d}: job {job} is not in the job list")
            if cc and not conn.execute("SELECT 1 FROM cost_codes WHERE code=?", (cc,)).fetchone():
                issues.append(f"{d}: cost code {cc} is not in the standard list")
            if unit and have_equipment_table and not conn.execute("SELECT 1 FROM equipment WHERE unit_id=?", (unit,)).fetchone():
                issues.append(f"{d}: unit {unit} is not in the fleet list")
            if not job:
                issues.append(f"{d}: a line has no job")
            if not (reg or ot or dt or eq):
                continue
            db.insert(conn, "time_entries", dict(timesheet_id=tsid, work_date=d.isoformat(), job_no=job, cost_code=cc, hours=reg, ot_hours=ot, dt_hours=dt,
                                                 equipment_id=unit, equipment_hours=eq, description=(ln.get("desc") or None)))
            lines_done += 1
            day_hours += reg + ot + dt
        if day_hours > MAX_HOURS_DAY:
            issues.append(f"{d}: {day_hours:g}h in one day")
        db.insert(conn, "timecard_days", dict(timesheet_id=tsid, work_date=d.isoformat(), loa=1 if day.get("loa") else 0, pickup=1 if day.get("pu") else 0,
                                              travel_km=_f(day.get("km")), notes=(day.get("notes") or None), supervisor=(payload.get("supervisor") or None),
                                              sent_at=sent_at, document_id=doc_id))
        days_done += 1

    tot = conn.execute("SELECT COALESCE(SUM(hours),0) h, COALESCE(SUM(ot_hours),0) ot FROM time_entries WHERE timesheet_id=?", (tsid,)).fetchone()
    conn.execute("UPDATE timesheets SET total_hours=?, total_ot_hours=?, status=? WHERE id=?", (tot["h"], tot["ot"], "validated" if not issues else "received", tsid))
    if issues:
        raise_item(conn, "timesheet_issue", f"Timecard {name} PP {pe}: {len(issues)} issue(s)", "\n".join(dict.fromkeys(issues)), "timesheets", tsid, priority=2)
    ensure_payroll_run(conn, settings, pe)
    conn.commit()
    return f"timecard {name} PP {pe}: {days_done} day(s), {lines_done} line(s), {len(issues)} issue(s)"


def filing_decision(payload: dict, sharepoint: dict, ext: str = "txt") -> FilingDecision:
    pe = _period_end(payload) or date.today()
    ds = sorted(d.get("date") for d in payload.get("days", []) if d.get("date"))
    span = ds[0] if len(ds) == 1 else (f"{ds[0]}_to_{ds[-1]}" if ds else "nodates")
    return FilingDecision(f"{sharepoint.get('timesheets', '04_PAYROLL/01_TIMESHEETS')}/{pe.strftime('%Y')}/PP_{pe.isoformat()}",
                          f"{pe.isoformat()}_{slug(payload['employee'], 30)}_Timecard_{span}.{ext}")


def export_reference(conn: sqlite3.Connection, settings, out_path: str | Path, submit_to: str = "accounts@ramexcavating.ca") -> dict:
    """Write timecards/app/data/reference.json from the database, so the phones follow the same job list ramfin does."""
    jobs = [dict(no=r["job_no"], name=r["name"], client=r["client"] or "") for r in db.rows(conn, "SELECT job_no, name, client FROM jobs WHERE status='active' ORDER BY job_no")]
    codes = [dict(code=r["code"], desc=r["description"], cat=r["category"] or "") for r in db.rows(conn, "SELECT code, description, category FROM cost_codes ORDER BY code")]
    units = [dict(unit=r["unit_id"], type=r["description"] or "") for r in db.rows(conn, "SELECT unit_id, description FROM equipment WHERE active=1 ORDER BY unit_id")]
    known = {c["code"] for c in codes}
    pay = settings.raw.get("forecast", {}).get("payroll", {})
    anchor_pay = parse_date(str(pay.get("anchor_pay_date", "")))
    # pay day is the Friday after the period ends on Saturday: the period end is the Saturday six days earlier
    anchor_end = (date.fromordinal(anchor_pay.toordinal() - 6)).isoformat() if anchor_pay else "2026-08-29"
    ref = dict(version=datetime.now(timezone.utc).strftime("%Y-%m-%d"), company=settings.raw.get("company", {}).get("name", "RAM Excavating Limited"),
               submitTo=submit_to, payPeriod=dict(anchorEnd=anchor_end, days=int(pay.get("cadence_days", 14))),
               allowances=dict(loa=220.0, pickup=150.0, travelKm=0.73), maxHoursDay=MAX_HOURS_DAY,
               jobs=jobs, equipment=units, costCodes=codes, favouriteCodes=[c for c in FAVOURITE_CODES if c in known])
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ref, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return dict(jobs=len(jobs), cost_codes=len(codes), equipment=len(units), path=str(p))


def allowance_rates(settings) -> dict:
    """LOA, own-truck and travel rates: config `company.allowances`, else the rates on the paper sheet."""
    raw = (getattr(settings, "company", None) or {}).get("allowances", {}) if settings is not None else {}
    return {**DEFAULT_ALLOWANCES, **{k: float(v) for k, v in (raw or {}).items()}}


def pay_period_summary(conn: sqlite3.Connection, settings, period_end: str | date) -> list[dict]:
    """One row per employee for the pay period: hours by type, allowance days, km, and the dollar amounts the paper
    timesheet's 'Amounts' row shows (OT at 1.5x, DT at 2x, allowances at the configured rates). Gross only; no burden."""
    pe = period_end.isoformat() if isinstance(period_end, date) else str(period_end)
    rates = allowance_rates(settings)
    out = []
    for ts in db.rows(conn, "SELECT ts.id, ts.status, e.name, e.position, e.base_rate FROM timesheets ts JOIN employees e ON e.id=ts.employee_id WHERE ts.period_end=? ORDER BY e.name", (pe,)):
        h = conn.execute("SELECT COALESCE(SUM(hours),0) reg, COALESCE(SUM(ot_hours),0) ot, COALESCE(SUM(dt_hours),0) dt, "
                         "COALESCE(SUM(CASE WHEN COALESCE(equipment_hours,0)>0 THEN equipment_hours ELSE 0 END),0) eq, COUNT(DISTINCT work_date) days "
                         "FROM time_entries WHERE timesheet_id=?", (ts["id"],)).fetchone()
        a = conn.execute("SELECT COALESCE(SUM(loa),0) loa, COALESCE(SUM(pickup),0) pu, COALESCE(SUM(travel_km),0) km FROM timecard_days WHERE timesheet_id=?", (ts["id"],)).fetchone()
        rate = float(ts["base_rate"] or 0)
        wages = round(h["reg"] * rate + h["ot"] * rate * 1.5 + h["dt"] * rate * 2.0, 2)
        allow = round(a["loa"] * rates["loa"] + a["pu"] * rates["pickup"] + a["km"] * rates["travel_km"], 2)
        out.append(dict(employee=ts["name"], position=ts["position"], status=ts["status"], base_rate=rate, days=h["days"], reg=h["reg"], ot=h["ot"], dt=h["dt"],
                        equipment_hours=h["eq"], loa_days=a["loa"], pickup_days=a["pu"], travel_km=a["km"], wages=wages, allowances=allow, gross=round(wages + allow, 2),
                        missing_rate=rate == 0))
    return out


def format_summary(rows: list[dict], period_end: str) -> str:
    if not rows:
        return f"No timesheets for pay period ending {period_end}."
    L = [f"Pay period ending {period_end}", "",
         f"{'Employee':<22}{'Days':>5}{'Reg':>7}{'OT':>6}{'DT':>6}{'Equip':>7}{'LOA':>5}{'P/U':>5}{'km':>7}{'Wages':>11}{'Allow.':>10}{'Gross':>11}  Status"]
    for r in rows:
        L.append(f"{r['employee'][:21]:<22}{r['days']:>5}{r['reg']:>7g}{r['ot']:>6g}{r['dt']:>6g}{r['equipment_hours']:>7g}{r['loa_days']:>5}{r['pickup_days']:>5}{r['travel_km']:>7g}"
                 f"{r['wages']:>11,.2f}{r['allowances']:>10,.2f}{r['gross']:>11,.2f}  {r['status']}{'  NO BASE RATE' if r['missing_rate'] else ''}")
    tot = {k: sum(r[k] for r in rows) for k in ("reg", "ot", "dt", "equipment_hours", "loa_days", "pickup_days", "travel_km", "wages", "allowances", "gross")}
    L.append(f"{'TOTAL':<22}{'':>5}{tot['reg']:>7g}{tot['ot']:>6g}{tot['dt']:>6g}{tot['equipment_hours']:>7g}{tot['loa_days']:>5}{tot['pickup_days']:>5}{tot['travel_km']:>7g}"
             f"{tot['wages']:>11,.2f}{tot['allowances']:>10,.2f}{tot['gross']:>11,.2f}")
    L += ["", "Gross before burden. Wages: Reg x rate, OT x 1.5, DT x 2. Allowances at the rates on the paper timesheet unless company.allowances overrides them."]
    return "\n".join(L)
