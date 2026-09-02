"""Rodney's rules from 2026-09-02: newer document wins, LOA/travel stay on the job, vendor defaults, personal vendors."""
from datetime import date, timedelta

from ramfin import db
from ramfin.ledger import intake, jobcost
from ramfin.models import Extraction
from ramfin.rules import hygiene, vendors
from tests.fixtures import extractions as fx


def _doc(conn, name):
    return db.insert(conn, "documents", dict(sha256=name, source="test", filename=name, status="new", created_at=db.now_iso()))


def _vendor(conn, name, **kw):
    vid = vendors.find_or_create(conn, name)
    for k, v in kw.items():
        conn.execute(f"UPDATE vendors SET {k}=? WHERE id=?", (v, vid))
    return vid


def test_newer_statement_total_only_collapses_register(conn, settings):
    vid = _vendor(conn, "Royalite Industrial Maintenance Ltd.")
    for no, amt, inv in (("9392", 603.68, "2020-06-22"), ("9394", 10133.12, "2020-06-25"), ("22684", 291.2, "2026-03-20")):
        db.insert(conn, "ap_invoices", dict(vendor_id=vid, invoice_no=no, invoice_date=inv, amount=amt, amount_confirmed=1, status="Unpaid", planned_pay_date="2026-09-14", created_at=db.now_iso()))
    st = {"doc_type": "vendor_statement", "confidence": 0.9, "legible": True, "vendor_name": "Royalite Industrial Maintenance Ltd.", "doc_date": "2026-09-01", "statement_end": "2026-09-01", "total": 1468.85}
    out = intake.record(conn, settings, _doc(conn, "stmt.pdf"), Extraction.from_dict(st), None, None)
    assert "applied (total only)" in out
    open_rows = conn.execute("SELECT SUM(amount) s, COUNT(*) n FROM ap_invoices WHERE vendor_id=? AND status='Unpaid'", (vid,)).fetchone()
    assert open_rows["n"] == 1 and round(open_rows["s"], 2) == 1468.85
    assert conn.execute("SELECT planned_pay_date FROM ap_invoices WHERE vendor_id=? AND status='Unpaid'", (vid,)).fetchone()["planned_pay_date"] == "2026-09-14"


def test_older_statement_leaves_hand_edited_register(conn, settings):
    vid = _vendor(conn, "Four Rivers Co-operative")
    db.insert(conn, "ap_invoices", dict(vendor_id=vid, invoice_no="FR-1", invoice_date="2026-08-01", amount=10000.0, amount_confirmed=0, status="Deferred (no-breach)",
                                        planned_pay_date="2026-09-14", created_at=db.now_iso(), updated_at=db.now_iso()))   # Rodney touched it today
    st = {"doc_type": "vendor_statement", "confidence": 0.9, "legible": True, "vendor_name": "Four Rivers Co-operative", "doc_date": "2026-08-20", "statement_end": "2026-08-20", "total": 8367.23}
    out = intake.record(conn, settings, _doc(conn, "fr.pdf"), Extraction.from_dict(st), None, None)
    assert "older than register" in out
    assert conn.execute("SELECT amount, status FROM ap_invoices WHERE invoice_no='FR-1'").fetchone()["amount"] == 10000.0


def test_newer_itemised_statement_marks_missing_paid_and_adds_new(conn, settings):
    vid = _vendor(conn, "Active Rent-All Ltd.")
    db.insert(conn, "ap_invoices", dict(vendor_id=vid, invoice_no="204889", invoice_date="2026-07-02", amount=116.48, amount_confirmed=1, status="Unpaid", planned_pay_date="2026-07-18", created_at=db.now_iso()))
    db.insert(conn, "ap_invoices", dict(vendor_id=vid, invoice_no="204893", invoice_date="2026-07-02", amount=680.64, amount_confirmed=1, status="Unpaid", planned_pay_date="2026-07-18", created_at=db.now_iso()))
    st = {"doc_type": "vendor_statement", "confidence": 0.9, "legible": True, "vendor_name": "Active Rent-All Ltd.", "doc_date": "2026-09-01", "statement_end": "2026-09-01", "total": 1523.99,
          "line_items": [{"description": "Invoice 204893", "amount": "680.64"}, {"description": "Invoice 207034", "amount": "133.23"}, {"description": "Invoice 207101", "amount": "710.12"}]}
    out = intake.record(conn, settings, _doc(conn, "ar.pdf"), Extraction.from_dict(st), None, None)
    assert "applied (itemised)" in out
    st_ = {r["invoice_no"]: r["status"] for r in conn.execute("SELECT invoice_no, status FROM ap_invoices WHERE vendor_id=?", (vid,))}
    assert st_["204889"] == "Paid" and st_["204893"] == "Unpaid" and st_["207034"] == "Unpaid" and st_["207101"] == "Unpaid"


def test_personal_vendor_receipt_kept_out_of_job_cost(conn, settings):
    _vendor(conn, "Mark Conlin RMT", category="personal")
    rc = {"doc_type": "receipt", "confidence": 0.9, "legible": True, "vendor_name": "Mark Conlin RMT", "doc_date": "2026-07-21", "total": 130.0}
    out = intake.record(conn, settings, _doc(conn, "rmt.html"), Extraction.from_dict(rc), None, None)
    assert "personal receipt" in out
    assert conn.execute("SELECT personal FROM receipts").fetchone()["personal"] == 1
    assert conn.execute("SELECT COUNT(*) n FROM action_items").fetchone()["n"] == 0
    assert jobcost.job_cost(conn, settings) == {}


def test_vendor_default_job_and_code(conn, settings):
    _vendor(conn, "The Den by Moonshine Coffee", default_job="250601-01", default_cost_code="50-020")
    conn.execute("INSERT INTO jobs(job_no, name, status) VALUES('250601-01','General Business Operations','active')")
    conn.execute("INSERT INTO cost_codes(code, description) VALUES('50-020','Meals')")
    rc = {"doc_type": "receipt", "confidence": 0.9, "legible": True, "vendor_name": "The Den by Moonshine Coffee", "doc_date": "2026-08-07", "total": 30.14}
    intake.record(conn, settings, _doc(conn, "den.html"), Extraction.from_dict(rc), None, None)
    r = conn.execute("SELECT job_no, cost_code FROM receipts").fetchone()
    assert r["job_no"] == "250601-01" and r["cost_code"] == "50-020"
    assert conn.execute("SELECT COUNT(*) n FROM action_items WHERE kind='uncoded_receipt'").fetchone()["n"] == 0


def test_hygiene_applies_defaults_retroactively(conn, settings):
    vid = _vendor(conn, "Apple Canada Inc.", default_job="250601-01", default_cost_code="50-212")
    conn.execute("INSERT INTO jobs(job_no, name, status) VALUES('250601-01','General Business Operations','active')")
    pid = _vendor(conn, "Mark Conlin RMT", category="personal")
    r1 = db.insert(conn, "receipts", dict(vendor_id=vid, receipt_date="2026-08-01", amount=55.99, created_at=db.now_iso()))
    r2 = db.insert(conn, "receipts", dict(vendor_id=pid, receipt_date="2026-07-21", amount=130.0, created_at=db.now_iso()))
    db.insert(conn, "action_items", dict(kind="uncoded_receipt", title="x", ref_table="receipts", ref_id=r2, priority=3, status="open", created_at=db.now_iso()))
    out = hygiene.apply(conn)
    assert out["vendor_defaults"] >= 3
    assert conn.execute("SELECT job_no, cost_code FROM receipts WHERE id=?", (r1,)).fetchone()["job_no"] == "250601-01"
    assert conn.execute("SELECT personal FROM receipts WHERE id=?", (r2,)).fetchone()["personal"] == 1
    assert conn.execute("SELECT status FROM action_items").fetchone()["status"] == "resolved"


def test_timesheet_header_job_fills_blank_days_but_never_overhead(conn, settings):
    ts = {**fx.TIMESHEET_ED, "handwritten_job_no": "240617",
          "time_entries": [{"work_date": "2026-07-27", "job_no": "", "cost_code": "", "hours": 8, "ot_hours": 0, "description": "LOA x, Travel 150 km"},
                           {"work_date": "2026-07-28", "job_no": "", "cost_code": "", "hours": 8, "ot_hours": 0, "description": "blank"}]}
    out = intake.record(conn, settings, _doc(conn, "ts.pdf"), Extraction.from_dict(ts), None, None)
    assert "0 issue(s)" in out
    assert {r["job_no"] for r in conn.execute("SELECT job_no FROM time_entries")} == {"240617"}
    ts2 = {**fx.TIMESHEET_ED, "period_end": "2026-08-15", "handwritten_job_no": None,
           "time_entries": [{"work_date": "2026-08-10", "job_no": "", "cost_code": "", "hours": 8, "ot_hours": 0, "description": "LOA"}]}
    out2 = intake.record(conn, settings, _doc(conn, "ts2.pdf"), Extraction.from_dict(ts2), None, None)
    assert "1 issue(s)" in out2
    assert "coded to the job worked" in conn.execute("SELECT detail FROM action_items WHERE kind='timesheet_issue'").fetchone()["detail"]
