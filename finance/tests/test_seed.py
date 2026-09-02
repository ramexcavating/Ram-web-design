import io
from datetime import date

from openpyxl import Workbook

from ramfin import db, seed
from ramfin.config import load_settings


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = Workbook(); wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    b = io.BytesIO(); wb.save(b); return b.getvalue()


def test_cost_codes_xlsx(conn):
    data = _xlsx({"Sheet1": [["1-000", "GENERAL REQUIREMENTS"], ["1-294", "Fuel for Equipment"], ["2-000", "SITEWORKS"], ["2-186", "Concrete Curb and Gutter"],
                             ["EX-000", "EXCAVATORS"], ["EX-43E", "Excavator 225"], ["junk", "x"]]})
    assert seed.load_cost_codes_xlsx(conn, data) == 6
    assert conn.execute("SELECT category FROM cost_codes WHERE code='2-186'").fetchone()["category"] == "Siteworks"


def test_ap_register_import_is_idempotent(conn):
    hdr = ["ID", "Doc Type", "Vendor", "Invoice / Ref #", "Invoice Date", "Terms", "Due Date", "Amount (CAD, incl GST)", "Amt Confirmed?", "Payment Status",
           "Planned Pay Date", "Date Paid", "Method", "Job #", "Cost Code", "Source Mailbox", "Email Date", "Email Subject", "Notes"]
    rows = [["RAM EXCAVATING LIMITED - ACCOUNTS PAYABLE REGISTER"], hdr,
            ["AP-0001", "Invoice", "KADA Contracting", "INV 9810", date(2026, 6, 10), "Net 30", date(2026, 7, 10), 641.36, "Yes", "Unpaid", date(2026, 7, 18), None, None, "260102", "1-042 - Equipment Mobe/Demobe", "accounts@", None, "July invoice", "carried"],
            ["AP-0002", "Invoice", "Online Curbing", "Kinchant", date(2026, 8, 20), "Net 30", date(2026, 9, 2), "$38,000.00", "No", "Deferred (no-breach)", date(2026, 10, 12), None, None, "240617", "2-186 - Concrete Curb and Gutter", "rmickey@", None, "", ""],
            ["AP-0003", "Statement", "Four Rivers Co-operative", "Aug stmt", date(2026, 8, 31), "Net 30", None, 8367.23, "Yes", "Reference only", None, None, None, None, None, None, None, "", ""]]
    data = _xlsx({"REGISTER": rows})
    st = seed.import_ap_register(conn, data)
    assert st["ap_new"] == 2
    st2 = seed.import_ap_register(conn, data)
    assert st2["ap_new"] == 0 and st2["ap_seen"] == 2
    oc = conn.execute("SELECT a.status, a.planned_pay_date, a.amount, a.amount_confirmed, a.job_no, a.cost_code, v.name FROM ap_invoices a JOIN vendors v ON v.id=a.vendor_id WHERE invoice_no='Kinchant'").fetchone()
    assert oc["status"] == "Deferred (no-breach)" and oc["planned_pay_date"] == "2026-10-12" and oc["amount"] == 38000.0 and oc["amount_confirmed"] == 0
    assert oc["job_no"] == "240617" and oc["cost_code"] == "2-186" and oc["name"] == "Online Curbing"


def test_cashflow_tool_import(conn, settings):
    ar_hdr = ["Customer", "Invoice #", "Invoice date", "Amount", "Expected collection date", "Status", "Date paid", "Notes"]
    ar = [ar_hdr,
          ["MDM Construction", "442 Kinchant St project 200617", date(2026, 8, 1), 21269.78, date(2026, 9, 11), "Open", None, "KEY RECEIPT"],
          ["Knappet Industries", "Aug 2026 billing", date(2026, 9, 1), 20000.0, date(2026, 10, 1), "Estimated", None, ""],
          ["Mass Construction Ltd.", "91+ days", date(2025, 12, 31), 724.50, None, "Doubtful", None, ""],
          ["NOTE", "QBO AR posting caught up", date(2026, 8, 9), None, None, "Info", None, ""],
          ["TOTAL OPEN AR", None, None, 98988.92, None, None, None, ""]]
    wi_hdr = ["Date", "RBC chequing", "TD chequing", "TD Direct Investing", "Undeposited / other", "TD Bus Visa", "Op. line drawn (+)", "Net position", "Notes", "Capital One MC"]
    wi = [wi_hdr, [date(2026, 8, 24), 18.87, 0, 10828.23, -2130.4, -25910.56, 55854.71, -82737.45, "", None],
          [date(2026, 8, 28), 17782, 0, 10288, 0, -23957, 57812, -63384, "", -9685]]
    st = seed.import_cashflow_tool(conn, _xlsx({"AR_TRACKER": ar, "WEEKLY_INPUT": wi}), settings)
    assert st["ar_new"] == 3 and st["balances"] == 6
    assert conn.execute("SELECT job_no FROM ar_invoices WHERE customer='MDM Construction'").fetchone()["job_no"] == "240617"
    assert conn.execute("SELECT status FROM ar_invoices WHERE customer='Knappet Industries'").fetchone()["status"] == "Estimate"
    b = {r["account_key"]: r["balance"] for r in conn.execute("SELECT account_key, balance FROM bank_balances WHERE as_of='2026-08-28'")}
    assert b["rbc_chq"] == 17782.0 and b["td_loc"] == 57812.0 and b["td_visa"] == 23957.0 and b["cap_one"] == 9685.0


def test_live_config_seeds():
    settings = load_settings("config/config.yaml")
    conn = db.connect(":memory:")
    n = seed.seed_from_config(conn, settings)
    assert n["jobs"] == 6 and n["debts"] >= 8 and n["recurring"] >= 3 and n["equipment"] >= 8
    assert settings.forecast["floor_amount"] == -60000
    assert conn.execute("SELECT sharepoint_folder FROM jobs WHERE job_no='240617'").fetchone()["sharepoint_folder"] == "01_ACTIVE_PROJECTS/240617_MDM_KSLIH"
