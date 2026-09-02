"""Weekly cash flow report content. One structure, rendered to markdown (email/docx) and to the workbook."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .. import db
from ..ledger import jobcost
from ..rules import matching
from ..rules.forecast import Forecast


def build_report(conn: sqlite3.Connection, settings, fc: Forecast) -> dict:
    today = fc.as_of
    wk_ago = (today - timedelta(days=7)).isoformat()
    open_ar = conn.execute("SELECT COALESCE(SUM(amount - paid_amount),0) s, COUNT(*) n FROM ar_invoices WHERE status IN ('Open','Partially Paid')").fetchone()
    est_ar = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM ar_invoices WHERE status='Estimate'").fetchone()["s"]
    doubtful = conn.execute("SELECT COALESCE(SUM(amount - paid_amount),0) s FROM ar_invoices WHERE status='Doubtful'").fetchone()["s"]
    open_ap = conn.execute("SELECT COALESCE(SUM(amount),0) s, COUNT(*) n FROM ap_invoices WHERE status NOT IN ('Paid','Void-Credit','Reference only')").fetchone()
    unconf = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM ap_invoices WHERE status NOT IN ('Paid','Void-Credit','Reference only') AND amount_confirmed=0").fetchone()["s"]
    no_date = conn.execute("SELECT COALESCE(SUM(amount),0) s, COUNT(*) n FROM ap_invoices WHERE status IN ('Unpaid','Scheduled','Partially Paid') AND planned_pay_date IS NULL").fetchone()
    overdue = conn.execute("SELECT COALESCE(SUM(amount),0) s, COUNT(*) n FROM ap_invoices WHERE status IN ('Unpaid','Scheduled','Partially Paid') AND due_date < ?", (today.isoformat(),)).fetchone()
    conc = db.rows(conn, "SELECT customer, SUM(amount - paid_amount) s FROM ar_invoices WHERE status IN ('Open','Partially Paid') GROUP BY customer ORDER BY s DESC LIMIT 2")
    top2 = sum(r["s"] for r in conc)
    new_docs = conn.execute("SELECT COUNT(*) n FROM documents WHERE created_at >= ?", (wk_ago,)).fetchone()["n"]
    new_receipts = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(amount),0) s FROM receipts WHERE created_at >= ?", (wk_ago,)).fetchone()
    new_ap = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(amount),0) s FROM ap_invoices WHERE created_at >= ?", (wk_ago,)).fetchone()
    matched, required = matching.capture_rate(conn, (today - timedelta(days=90)).isoformat())
    open_actions = db.rows(conn, "SELECT priority, COUNT(*) n FROM action_items WHERE status='open' GROUP BY priority")
    actions = {r["priority"]: r["n"] for r in open_actions}
    jc = jobcost.job_cost(conn, settings, (today - timedelta(days=120)).isoformat(), today.isoformat())
    ec = jobcost.equipment_cost(conn, settings, (today - timedelta(days=120)).isoformat(), today.isoformat())
    fy_start = date(today.year if today.month > 5 else today.year - 1, 6, 1)
    hb = conn.execute("SELECT COALESCE(SUM(holdback),0) s FROM ar_invoices WHERE holdback>0 AND status<>'Paid'").fetchone()["s"]

    position = fc.opening_cash - fc.loc_drawn
    if fc.breach_weeks:
        headline = f"{fc.breach_weeks} of {len(fc.weeks)} weeks breach the floor after deferrals; lowest ${fc.lowest:,.0f}. Decisions needed."
    elif fc.deferrals:
        headline = f"No breach weeks after moving {len(fc.deferrals)} payable(s). Lowest week ${fc.lowest:,.0f}. Confirm the deferrals with suppliers."
    else:
        headline = f"No breach weeks. Lowest week ${fc.lowest:,.0f}. Position ${position:,.0f}."
    return dict(
        as_of=today.isoformat(), headline=headline, position=position, cash=fc.opening_cash, loc_drawn=fc.loc_drawn,
        loc_limit=float(settings.forecast.get("loc_limit", 60000)), headroom=float(settings.forecast.get("loc_limit", 60000)) - fc.loc_drawn,
        lowest=fc.lowest, breach_weeks=fc.breach_weeks, floor=fc.floor, basis=fc.basis,
        open_ar=open_ar["s"], open_ar_n=open_ar["n"], estimated_ar=est_ar, doubtful_ar=doubtful,
        ar_concentration=(top2 / open_ar["s"]) if open_ar["s"] else 0.0, holdback_receivable=hb,
        open_ap=open_ap["s"], open_ap_n=open_ap["n"], unconfirmed_ap=unconf, no_date_ap=no_date["s"], no_date_ap_n=no_date["n"],
        overdue_ap=overdue["s"], overdue_ap_n=overdue["n"],
        new_docs=new_docs, new_receipts_n=new_receipts["n"], new_receipts=new_receipts["s"], new_ap_n=new_ap["n"], new_ap=new_ap["s"],
        capture_rate=(matched / required) if required else None, capture_matched=matched, capture_required=required,
        actions_today=actions.get(1, 0), actions_week=actions.get(2, 0), actions_later=actions.get(3, 0),
        deferrals=fc.deferrals, warnings=fc.warnings, weeks=fc.weeks, job_cost=jc, equipment_cost=ec, fiscal_year_start=fy_start.isoformat(),
    )


def to_markdown(r: dict) -> str:
    L = [f"# RAM Excavating - Weekly Cash Flow Report - {r['as_of']}", "", f"**{r['headline']}**", "", "## Where the cash is"]
    L += [f"- Cash in bank: ${r['cash']:,.2f}", f"- Operating line drawn: ${r['loc_drawn']:,.2f} of ${r['loc_limit']:,.0f} (headroom ${r['headroom']:,.2f})",
          f"- Position (cash minus line): ${r['position']:,.2f}", f"- Lowest projected {r['basis']} in {len(r['weeks'])} weeks: ${r['lowest']:,.2f} against a floor of ${r['floor']:,.0f}",
          "", "## 13-week view", "", "| Week | Opening | In | Out | Closing | Status |", "|---|---:|---:|---:|---:|---|"]
    for w in r["weeks"]:
        L.append(f"| {w.start} | {w.opening:,.0f} | {w.inflows:,.0f} | {w.outflows:,.0f} | {w.closing:,.0f} | {w.status} |")
    L += ["", "## Receivables", f"- Open AR: ${r['open_ar']:,.2f} across {r['open_ar_n']} invoice(s); top-2 customer concentration {r['ar_concentration']:.0%}",
          f"- Estimated (not yet invoiced) billings in the forecast: ${r['estimated_ar']:,.2f}", f"- Doubtful: ${r['doubtful_ar']:,.2f}",
          f"- Holdback receivable outstanding: ${r['holdback_receivable']:,.2f}", "", "## Payables",
          f"- Open AP (register basis): ${r['open_ap']:,.2f} across {r['open_ap_n']} item(s)", f"- Of which unconfirmed amounts (estimates): ${r['unconfirmed_ap']:,.2f}",
          f"- Of which NO planned pay date (invisible to forecast): ${r['no_date_ap']:,.2f} ({r['no_date_ap_n']})",
          f"- Overdue: ${r['overdue_ap']:,.2f} ({r['overdue_ap_n']})"]
    if r["deferrals"]:
        L += ["", "## DEFERRED AP - ACTION REQUIRED (no-breach rule)"]
        L += [f"- {d['label']} ${d['amount']:,.2f}: {d['from_date']} to {d['to_date']}. {d['reason']}." for d in r["deferrals"]]
    if r["warnings"]:
        L += ["", "## Data quality"] + [f"- {w}" for w in r["warnings"]]
    L += ["", "## This week's intake", f"- {r['new_docs']} documents captured; {r['new_receipts_n']} receipts (${r['new_receipts']:,.2f}); {r['new_ap_n']} vendor invoices (${r['new_ap']:,.2f})"]
    if r["capture_rate"] is not None:
        L.append(f"- Receipt capture rate, last 90 days: {r['capture_rate']:.0%} ({r['capture_matched']} of {r['capture_required']} purchases have a receipt or invoice)")
    L += ["", "## Job cost, last 120 days (net of GST)", "", "| Job | Labour | Receipts | Invoices | Total | Billed | Margin to date |", "|---|---:|---:|---:|---:|---:|---:|"]
    for j, v in sorted(r["job_cost"].items(), key=lambda kv: -kv[1]["total"]):
        L.append(f"| {j} {v['name']} | {v['labour']:,.0f} | {v['receipts']:,.0f} | {v['invoices']:,.0f} | {v['total']:,.0f} | {v['billed']:,.0f} | {v['margin_to_date']:,.0f} |")
    if r.get("equipment_cost"):
        L += ["", "## Equipment, last 120 days (net of GST)", "", "| Unit | Repairs | Fuel | Other | Total | Hours | $/hr |", "|---|---:|---:|---:|---:|---:|---:|"]
        for u, v in sorted(r["equipment_cost"].items(), key=lambda kv: -kv[1]["total"]):
            L.append(f"| {u} {v['description'] or ''} | {v['repairs']:,.0f} | {v['fuel']:,.0f} | {v['other']:,.0f} | {v['total']:,.0f} | {v['hours']:,.0f} | {v['cost_per_hour'] if v['cost_per_hour'] is not None else '-'} |")
    L += ["", "## Needs your input", f"- Today: {r['actions_today']}   This week: {r['actions_week']}   When convenient: {r['actions_later']}", ""]
    return "\n".join(L)
