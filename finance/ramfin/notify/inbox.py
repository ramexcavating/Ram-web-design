"""The 'needs your input' queue. Everything the system cannot decide on its own lands here, once, with a priority.
Rodney sees it three ways: the daily digest email, the ACTIONS tab of the weekly workbook, and `ramfin inbox`."""
from __future__ import annotations

import sqlite3

from .. import db

PRIORITY_LABEL = {1: "TODAY", 2: "THIS WEEK", 3: "WHEN CONVENIENT"}


def raise_item(conn: sqlite3.Connection, kind: str, title: str, detail: str | None, ref_table: str | None, ref_id: int | None, priority: int = 2) -> int | None:
    existing = conn.execute("SELECT id, status FROM action_items WHERE kind=? AND ref_table IS ? AND ref_id IS ?", (kind, ref_table, ref_id)).fetchone()
    if existing:
        if existing["status"] == "open":
            conn.execute("UPDATE action_items SET title=?, detail=?, priority=MIN(priority, ?) WHERE id=?", (title, detail, priority, existing["id"]))
        return existing["id"]
    return db.insert(conn, "action_items", dict(kind=kind, title=title[:200], detail=detail, ref_table=ref_table, ref_id=ref_id,
                                                priority=priority, status="open", created_at=db.now_iso()))


def resolve(conn: sqlite3.Connection, item_id: int, status: str = "resolved") -> None:
    conn.execute("UPDATE action_items SET status=?, resolved_at=? WHERE id=?", (status, db.now_iso(), item_id))
    conn.commit()


def open_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.rows(conn, "SELECT * FROM action_items WHERE status='open' ORDER BY priority, created_at")


def auto_resolve(conn: sqlite3.Connection) -> int:
    """Close items whose underlying condition has cleared (a receipt got coded, an invoice got an amount, a line got matched)."""
    n = 0
    checks = [
        ("uncoded_receipt", "receipts", "SELECT 1 FROM receipts WHERE id=? AND job_no IS NOT NULL AND cost_code IS NOT NULL"),
        ("illegible", "receipts", "SELECT 1 FROM receipts WHERE id=? AND amount IS NOT NULL"),
        ("unconfirmed_amount", "ap_invoices", "SELECT 1 FROM ap_invoices WHERE id=? AND amount IS NOT NULL AND amount_confirmed=1"),
        ("no_pay_date", "ap_invoices", "SELECT 1 FROM ap_invoices WHERE id=? AND (planned_pay_date IS NOT NULL OR status IN ('Paid','Void-Credit','Reference only','Disputed','On Hold'))"),
        ("missing_receipt", "bank_transactions", "SELECT 1 FROM bank_transactions WHERE id=? AND (match_type IN ('receipt','ap','rule') OR receipt_required=0)"),
        ("unmatched_deposit", "bank_transactions", "SELECT 1 FROM bank_transactions WHERE id=? AND match_type IN ('ar','rule')"),
        ("timesheet_issue", "timesheets", "SELECT 1 FROM timesheets WHERE id=? AND status IN ('validated','sent_to_payroll','paid')"),
    ]
    for kind, table, sql in checks:
        for it in db.rows(conn, "SELECT id, ref_id FROM action_items WHERE status='open' AND kind=? AND ref_table=?", (kind, table)):
            ref = it["ref_id"] if it["ref_id"] < 1_000_000 else it["ref_id"] - 1_000_000
            if conn.execute(sql, (ref,)).fetchone():
                conn.execute("UPDATE action_items SET status='resolved', resolved_at=? WHERE id=?", (db.now_iso(), it["id"]))
                n += 1
    conn.commit()
    return n


def digest_html(conn: sqlite3.Connection, forecast=None, report=None) -> tuple[str, str]:
    """(subject, html). Short on purpose: what changed, what needs a decision, one line each."""
    items = open_items(conn)
    p1 = [i for i in items if i["priority"] == 1]
    subject = f"RAM finance: {len(p1)} for today, {len(items)} open" if items else "RAM finance: nothing needs you today"
    parts = ["<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px;max-width:760px'>"]
    if forecast is not None:
        lowest = forecast.lowest
        colour = "#b00020" if forecast.breach_weeks else ("#a36a00" if any(w.status == "TIGHT" for w in forecast.weeks) else "#1b7f3b")
        parts.append(f"<h2 style='margin:0 0 6px'>Cash</h2><p style='margin:0 0 10px'>Position ${forecast.opening_cash - forecast.loc_drawn:,.0f} "
                     f"(cash ${forecast.opening_cash:,.0f}, line drawn ${forecast.loc_drawn:,.0f}). "
                     f"<b style='color:{colour}'>Lowest week in the next {len(forecast.weeks)}: ${lowest:,.0f}; {forecast.breach_weeks} breach week(s).</b></p>")
        if forecast.deferrals:
            parts.append("<p style='margin:0 0 10px'><b>Moved under the no-breach rule:</b><br>" + "<br>".join(
                f"{d['label']} ${d['amount']:,.2f}: {d['from_date']} to {d['to_date']}" for d in forecast.deferrals) + "</p>")
        if forecast.warnings:
            parts.append("<p style='margin:0 0 10px;color:#a36a00'>" + "<br>".join(forecast.warnings[:6]) + "</p>")
    if report:
        parts.append(f"<p style='margin:0 0 10px'>{report.get('headline','')}</p>")
    for pr in (1, 2, 3):
        group = [i for i in items if i["priority"] == pr]
        if not group:
            continue
        parts.append(f"<h3 style='margin:14px 0 4px'>{PRIORITY_LABEL[pr]} ({len(group)})</h3><ol style='margin:0;padding-left:20px'>")
        for i in group[:25]:
            parts.append(f"<li style='margin:2px 0'><b>{i['title']}</b>" + (f"<br><span style='color:#555'>{(i['detail'] or '')[:300]}</span>" if i["detail"] else "") + f" <span style='color:#999'>#{i['id']}</span></li>")
        if len(group) > 25:
            parts.append(f"<li>... and {len(group) - 25} more in the workbook</li>")
        parts.append("</ol>")
    parts.append("<p style='color:#999;margin-top:16px'>Reply with the item number and your answer, or edit the green columns in the review workbook. Both get read back in.</p></div>")
    return subject, "".join(parts)
