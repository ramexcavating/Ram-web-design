from ramfin import db
from ramfin.ledger import intake, jobcost, timesheets
from ramfin.models import Extraction
from ramfin.notify.inbox import open_items
from tests.fixtures import extractions as fx


def _doc(conn, name):
    return db.insert(conn, "documents", dict(sha256=name, source="test", filename=name, status="new", created_at=db.now_iso()))


def test_receipt_with_handwritten_job_and_code(conn, settings):
    intake.record(conn, settings, _doc(conn, "a"), Extraction.from_dict(fx.RECEIPT_HOME_HARDWARE), None, None)
    r = conn.execute("SELECT * FROM receipts").fetchone()
    assert r["job_no"] == "240617" and r["cost_code"] == "04-100" and r["amount"] == 94.66
    assert not [i for i in open_items(conn) if i["kind"] == "uncoded_receipt"]


def test_receipt_without_job_raises_action(conn, settings):
    intake.record(conn, settings, _doc(conn, "b"), Extraction.from_dict(fx.RECEIPT_NO_JOB), None, "fuel run")
    kinds = [i["kind"] for i in open_items(conn)]
    assert "uncoded_receipt" in kinds


def test_vendor_invoice_terms_and_duplicate(conn, settings):
    intake.record(conn, settings, _doc(conn, "c"), Extraction.from_dict(fx.INVOICE_BRANDT), "ar@brandt.ca", None)
    a = conn.execute("SELECT * FROM ap_invoices").fetchone()
    assert a["amount"] == 3276.0 and a["amount_confirmed"] == 1 and a["planned_pay_date"] == "2026-09-11" and a["status"] == "Unpaid"
    intake.record(conn, settings, _doc(conn, "c2"), Extraction.from_dict(fx.INVOICE_BRANDT), "ar@brandt.ca", None)
    assert conn.execute("SELECT COUNT(*) n FROM ap_invoices").fetchone()["n"] == 1
    assert any(i["kind"] == "decision" and "duplicate" in i["title"] for i in open_items(conn))


def test_invoice_without_amount_flags(conn, settings):
    intake.record(conn, settings, _doc(conn, "d"), Extraction.from_dict(fx.INVOICE_NO_AMOUNT), "noreply@leasedirect.ca", None)
    assert any(i["kind"] == "unconfirmed_amount" for i in open_items(conn))


def test_job_matched_from_invoice_notes(conn, settings):
    intake.record(conn, settings, _doc(conn, "e"), Extraction.from_dict(fx.INVOICE_CURBING), None, None)
    assert conn.execute("SELECT job_no FROM ap_invoices").fetchone()["job_no"] == "240617"


def test_timesheet_entries_and_issues(conn, settings):
    out = intake.record(conn, settings, _doc(conn, "t"), Extraction.from_dict(fx.TIMESHEET_ED), None, None)
    assert "36.0h + 2.0h OT" in out
    entries = db.rows(conn, "SELECT * FROM time_entries ORDER BY work_date")
    assert entries[2]["job_no"] == "260102"          # 'Dunkley' name resolved to job number
    assert entries[3]["job_no"] is None              # 'shop' has no job -> issue raised
    assert any(i["kind"] == "timesheet_issue" for i in open_items(conn))
    assert conn.execute("SELECT pay_date FROM payroll_runs WHERE period_end='2026-08-01'").fetchone()["pay_date"] == "2026-08-07"
    acc = timesheets.payroll_accrual(conn, settings, "2026-08-01")
    assert acc["gross"] == 36 * 28 + 2 * 28 * 1.5
    jc = jobcost.job_cost(conn, settings)
    assert jc["240617"]["labour_hours"] == 22 and jc["260102"]["labour"] == round(8 * 28 * 1.35, 2)


def test_customer_payment_marks_invoice_paid(conn, settings):
    db.insert(conn, "ar_invoices", dict(customer="IDL", invoice_no="600", amount=15120.0, status="Open", expected_date="2026-08-21", created_at=db.now_iso()))
    intake.record(conn, settings, _doc(conn, "p"), Extraction.from_dict(fx.CUSTOMER_PAYMENT_IDL), None, None)
    a = conn.execute("SELECT status, paid_amount FROM ar_invoices").fetchone()
    assert a["status"] == "Paid" and a["paid_amount"] == 15120.0


def test_bank_statement_extraction_imports_lines(conn, settings):
    intake.record(conn, settings, _doc(conn, "bk"), Extraction.from_dict(fx.BANK_STATEMENT_TD), None, None)
    assert conn.execute("SELECT COUNT(*) n FROM bank_transactions WHERE account_key='td_chq'").fetchone()["n"] == 4
    assert conn.execute("SELECT balance FROM bank_balances WHERE account_key='td_chq'").fetchone()["balance"] == 2650.34
