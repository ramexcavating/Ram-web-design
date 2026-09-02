"""13-week cash flow forecast and the NO-BREACH rule.

Position basis: cash in bank accounts minus operating line drawn (the way the existing tool defines it).
Floor: configurable. The company procedure RAM-10-PR-10 describes a $60K minimum; the existing workbook grades a
week OK when the position closes above zero (i.e. the $60K line is what is being protected). `forecast.floor_amount`
in config decides which reading applies. Breaches are resolved by moving DISCRETIONARY payables only - never payroll,
CRA, debt minimums, WorkSafeBC or vendors flagged critical.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from .. import db
from .filing import parse_date

NEVER_DEFER = {"payroll", "cra", "debt", "wsbc", "critical_vendor", "tax"}


@dataclass
class Line:
    kind: str          # ar | ap | payroll | cra | debt | recurring
    ref_id: int | None
    label: str
    amount: float      # positive in, negative out
    on: date
    deferrable: bool = False
    confirmed: bool = True


@dataclass
class Week:
    start: date
    end: date
    opening: float = 0.0
    inflows: float = 0.0
    outflows: float = 0.0
    closing: float = 0.0
    status: str = "OK"
    lines: list[Line] = field(default_factory=list)


@dataclass
class Forecast:
    as_of: date
    basis: str
    floor: float
    opening_cash: float
    loc_drawn: float
    weeks: list[Week]
    deferrals: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    balances: dict[str, tuple[str, float]] = field(default_factory=dict)

    @property
    def lowest(self) -> float:
        return min(w.closing for w in self.weeks) if self.weeks else self.opening_cash

    @property
    def breach_weeks(self) -> int:
        return sum(1 for w in self.weeks if w.status == "BREACH")


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def latest_balances(conn: sqlite3.Connection, settings) -> dict[str, tuple[str, float]]:
    out = {}
    for a in settings.bank_accounts:
        r = conn.execute("SELECT as_of, balance FROM bank_balances WHERE account_key=? ORDER BY as_of DESC, created_at DESC LIMIT 1", (a.key,)).fetchone()
        if r:
            out[a.key] = (r["as_of"], float(r["balance"]))
    return out


def opening_position(conn: sqlite3.Connection, settings, warnings: list[str]) -> tuple[float, float, dict]:
    bals = latest_balances(conn, settings)
    cash = 0.0
    loc = 0.0
    for a in settings.bank_accounts:
        if a.key not in bals:
            if a.kind in ("chequing", "loc"):
                warnings.append(f"No balance on file for {a.name}. Enter one (ramfin balance {a.key} <amount>) before trusting this forecast.")
            continue
        as_of, bal = bals[a.key]
        if a.kind == "chequing":
            cash += bal
        elif a.kind == "loc":
            loc += bal
        if (date.today() - parse_date(as_of)).days > 10 and a.kind in ("chequing", "loc", "card"):
            warnings.append(f"{a.name} balance is {(date.today() - parse_date(as_of)).days} days old (as of {as_of}).")
    return cash, loc, bals


def _payroll_lines(settings, start: date, end: date) -> list[Line]:
    p = settings.forecast.get("payroll", {})
    cad = int(p.get("cadence_days", 14))
    anchor = settings.payroll_anchor()
    net = float(p.get("estimated_net_per_run", 0))
    out = []
    d = anchor
    while d > start:
        d -= timedelta(days=cad)
    while d <= end:
        if d >= start:
            out.append(Line("payroll", None, "Payroll (net, estimated)", -net, d, deferrable=False, confirmed=False))
        d += timedelta(days=cad)
    # CRA source deductions on the 15th
    remit = float(p.get("estimated_cra_remit", 0))
    day = int(p.get("cra_remit_day_of_month", 15))
    m = date(start.year, start.month, 1)
    while m <= end:
        due = m.replace(day=min(day, 28))
        if start <= due <= end and remit:
            out.append(Line("cra", None, "CRA source deductions", -remit, due, deferrable=False, confirmed=False))
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def _debt_lines(conn: sqlite3.Connection, start: date, end: date) -> list[Line]:
    out = []
    for d in db.rows(conn, "SELECT * FROM debts WHERE monthly_payment>0"):
        m = date(start.year, start.month, 1)
        while m <= end:
            due = m.replace(day=min(int(d["payment_day"] or 1), 28))
            if start <= due <= end:
                out.append(Line("debt", d["id"], f"{d['name']} payment", -float(d["monthly_payment"]), due, deferrable=False))
            m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def _recurring_lines(conn: sqlite3.Connection, start: date, end: date) -> list[Line]:
    out = []
    step = {"weekly": 7, "biweekly": 14}
    for r in db.rows(conn, "SELECT * FROM recurring"):
        d = parse_date(r["next_date"])
        stop = parse_date(r["end_date"]) or end
        sign = 1 if r["direction"] == "in" else -1
        while d and d <= min(end, stop):
            if d >= start:
                out.append(Line("recurring", r["id"], r["name"], sign * float(r["amount"]), d, deferrable=False, confirmed=False))
            if r["cadence"] in step:
                d += timedelta(days=step[r["cadence"]])
            else:
                nm = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
                d = nm.replace(day=min(d.day, 28))
    return out


def build_lines(conn: sqlite3.Connection, settings, start: date, end: date) -> list[Line]:
    lines: list[Line] = []
    for a in db.rows(conn, "SELECT id, customer, invoice_no, amount - paid_amount AS bal, expected_date, due_date, status FROM ar_invoices "
                           "WHERE status IN ('Open','Partially Paid','Estimate')"):
        on = parse_date(a["expected_date"]) or parse_date(a["due_date"])
        if on is None:
            continue
        if on < start:
            on = start
        if on <= end:
            lines.append(Line("ar", a["id"], f"{a['customer']} inv {a['invoice_no'] or '?'}", float(a["bal"]), on, confirmed=a["status"] != "Estimate"))
    for p in db.rows(conn, "SELECT a.*, v.critical, v.category vcat FROM ap_invoices a LEFT JOIN vendors v ON v.id=a.vendor_id "
                           "WHERE a.status IN ('Unpaid','Scheduled','Partially Paid','Deferred (no-breach)')"):
        on = parse_date(p["planned_pay_date"])
        if on is None:
            continue
        if on < start:
            on = start
        if on <= end and p["amount"]:
            never = (p["category"] in NEVER_DEFER) or (p["vcat"] in ("payroll", "cra", "debt")) or bool(p["critical"])
            vend = conn.execute("SELECT name FROM vendors WHERE id=?", (p["vendor_id"],)).fetchone()
            lines.append(Line("ap", p["id"], f"{vend['name'] if vend else 'Vendor'} inv {p['invoice_no'] or '?'}", -float(p["amount"]), on,
                              deferrable=not never, confirmed=bool(p["amount_confirmed"])))
    lines += _payroll_lines(settings, start, end)
    lines += _debt_lines(conn, start, end)
    lines += _recurring_lines(conn, start, end)
    return lines


def roll(fc: Forecast, lines: list[Line]) -> None:
    pos = fc.opening_cash - fc.loc_drawn if fc.basis == "position" else fc.opening_cash
    for w in fc.weeks:
        w.lines = [ln for ln in lines if w.start <= ln.on <= w.end]
        w.opening = pos
        w.inflows = sum(ln.amount for ln in w.lines if ln.amount > 0)
        w.outflows = -sum(ln.amount for ln in w.lines if ln.amount < 0)
        pos = w.opening + w.inflows - w.outflows
        w.closing = pos
        tight = float(fc.floor) + float(getattr(fc, "_tight", 10000))
        w.status = "BREACH" if w.closing < fc.floor else ("TIGHT" if w.closing < tight else "OK")


def build_forecast(conn: sqlite3.Connection, settings, as_of: date | None = None) -> Forecast:
    as_of = as_of or date.today()
    start = monday_of(as_of)
    horizon = int(settings.forecast.get("horizon_weeks", 13))
    warnings: list[str] = []
    cash, loc, bals = opening_position(conn, settings, warnings)
    fc = Forecast(as_of=as_of, basis=settings.forecast.get("basis", "position"), floor=float(settings.forecast.get("floor_amount", 0)),
                  opening_cash=cash, loc_drawn=loc, weeks=[Week(start + timedelta(days=7 * i), start + timedelta(days=7 * i + 6)) for i in range(horizon)],
                  warnings=warnings, balances=bals)
    fc._tight = float(settings.forecast.get("tight_band", 10000))  # type: ignore[attr-defined]
    end = fc.weeks[-1].end
    lines = build_lines(conn, settings, start, end)
    invisible = db.rows(conn, "SELECT COALESCE(SUM(amount),0) s, COUNT(*) n FROM ap_invoices WHERE status IN ('Unpaid','Scheduled','Partially Paid') AND planned_pay_date IS NULL")[0]
    if invisible["n"]:
        warnings.append(f"{invisible['n']} unpaid payables totalling ${invisible['s']:,.2f} have no planned pay date and are INVISIBLE to this forecast.")
    unknown = conn.execute("SELECT COUNT(*) n FROM ap_invoices WHERE status IN ('Unpaid','Scheduled') AND (amount IS NULL OR amount=0)").fetchone()["n"]
    if unknown:
        warnings.append(f"{unknown} unpaid payables have no amount at all (portal-only or blank-subject invoices).")
    roll(fc, lines)
    return fc


def apply_no_breach(conn: sqlite3.Connection, settings, fc: Forecast, dry_run: bool = False) -> Forecast:
    """Move the largest discretionary payable out of each breach week to the first later week that stays above the
    floor. Record every move; nothing critical is ever touched."""
    lines = [ln for w in fc.weeks for ln in w.lines]
    moved: list[dict] = []
    for _ in range(200):
        roll(fc, lines)
        breach = next((w for w in fc.weeks if w.status == "BREACH"), None)
        if not breach:
            break
        cands = sorted([ln for ln in breach.lines if ln.kind == "ap" and ln.deferrable and ln.amount < 0], key=lambda x: x.amount)
        if not cands:
            fc.warnings.append(f"Week of {breach.start} breaches by ${fc.floor - breach.closing:,.2f} and has no discretionary AP left to move. "
                               "Needs a collection, a draw, or a decision.")
            break
        ln = cands[0]
        deficit = fc.floor - breach.closing
        target = None
        for w in fc.weeks:
            if w.start <= breach.start:
                continue
            if w.closing + ln.amount >= fc.floor or w is fc.weeks[-1]:   # ln.amount is negative; test the landing
                target = w
                break
        if target is None:
            fc.warnings.append(f"Could not find a landing week for {ln.label} ${-ln.amount:,.2f}. It stays in the week of {breach.start}.")
            ln.deferrable = False
            continue
        old_on = ln.on
        ln.on = target.start + timedelta(days=1)   # Tuesday of the landing week
        moved.append(dict(ap_id=ln.ref_id, label=ln.label, amount=-ln.amount, from_date=old_on.isoformat(), to_date=ln.on.isoformat(),
                          reason=f"week of {breach.start} would close ${deficit:,.2f} below the floor"))
    roll(fc, lines)
    fc.deferrals = moved
    if not dry_run:
        from ..notify.inbox import raise_item
        for m in moved:
            conn.execute("UPDATE ap_invoices SET original_planned_pay_date=COALESCE(original_planned_pay_date, planned_pay_date), "
                         "planned_pay_date=?, status='Deferred (no-breach)' WHERE id=?", (m["to_date"], m["ap_id"]))
            raise_item(conn, "deferral_to_confirm", f"Deferred {m['label']} ${m['amount']:,.2f} from {m['from_date']} to {m['to_date']}",
                       m["reason"] + ". Agree the new date with the supplier in writing; a silent slide on a sub carries lien risk.",
                       "ap_invoices", m["ap_id"], priority=1)
        conn.commit()
    return fc
