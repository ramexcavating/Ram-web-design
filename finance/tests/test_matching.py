from ramfin import db
from ramfin.ledger import intake
from ramfin.models import Extraction
from ramfin.notify.inbox import auto_resolve, open_items
from ramfin.rules import matching
from ramfin.sources import bank_import
from tests.fixtures import extractions as fx

TD_CSV = """07/03/2026,HOME HARDWARE QUESNEL,94.66,,3905.34
07/05/2026,MONTHLY ACCOUNT FEE,35.00,,3870.34
07/09/2026,PRINCESS AUTO,220.00,,3650.34
07/15/2026,EFT CREDIT IDL,,15120.00,18770.34
07/20/2026,TD VISA PAYMENT - THANK YOU,1400.56,,17369.78
"""
RBC_CSV = """"Account Type","Account Number","Transaction Date","Cheque Number","Description 1","Description 2","CAD$","USD$"
Chequing,12345,8/21/2026,,"E-TRANSFER RECEIVED","IDL",15120.00,
Chequing,12345,8/22/2026,,"BRANDT TRACTOR","",-3276.00,
"""


def test_td_csv_parses_and_dedupes(conn):
    found, new = bank_import.import_csv(conn, "td_chq", "td_csv", TD_CSV)
    assert (found, new) == (5, 5)
    found, new = bank_import.import_csv(conn, "td_chq", "td_csv", TD_CSV)
    assert new == 0
    assert conn.execute("SELECT balance FROM bank_balances WHERE account_key='td_chq'").fetchone()["balance"] == 17369.78


def test_rbc_csv_signs():
    lines = bank_import.parse_rbc_csv(RBC_CSV)
    assert lines[0]["amount"] == 15120.0 and lines[1]["amount"] == -3276.0 and lines[1]["txn_date"] == "2026-08-22"


def test_categorise_rules():
    assert matching.categorise("MONTHLY ACCOUNT FEE", -35) == ("fee", 0)
    assert matching.categorise("TD VISA PAYMENT - THANK YOU", -1400) == ("card_payment", 0)
    assert matching.categorise("PRINCESS AUTO", -220) == ("purchase", 1)
    assert matching.categorise("EFT CREDIT IDL", 15120) == ("deposit", 0)


def test_matching_receipt_ap_ar_and_missing(conn, settings):
    doc = db.insert(conn, "documents", dict(sha256="x", source="t", filename="x", status="new", created_at=db.now_iso()))
    intake.record(conn, settings, doc, Extraction.from_dict({**fx.RECEIPT_HOME_HARDWARE, "doc_date": "2026-07-02"}), None, None)
    intake.record(conn, settings, doc, Extraction.from_dict({**fx.INVOICE_BRANDT, "doc_date": "2026-08-12"}), None, None)
    db.insert(conn, "ar_invoices", dict(customer="IDL", invoice_no="600", amount=15120.0, status="Open", expected_date="2026-07-15", created_at=db.now_iso()))
    bank_import.import_csv(conn, "td_chq", "td_csv", TD_CSV)
    bank_import.import_csv(conn, "rbc_chq", "rbc_csv", RBC_CSV)
    stats = matching.match_transactions(conn)
    assert stats["receipt"] == 1 and stats["ap"] == 1 and stats["ar"] >= 1
    assert conn.execute("SELECT status FROM ap_invoices").fetchone()["status"] == "Paid"
    assert conn.execute("SELECT status FROM ar_invoices").fetchone()["status"] == "Paid"
    missing = [i for i in open_items(conn) if i["kind"] == "missing_receipt"]
    assert len(missing) == 1 and "PRINCESS AUTO" in missing[0]["title"]
    matched, required = matching.capture_rate(conn)
    assert (matched, required) == (2, 3)
    # user later photographs the Princess Auto receipt -> item auto-resolves
    doc2 = db.insert(conn, "documents", dict(sha256="y", source="t", filename="y", status="new", created_at=db.now_iso()))
    intake.record(conn, settings, doc2, Extraction.from_dict({"doc_type": "receipt", "confidence": 0.9, "legible": True, "vendor_name": "Princess Auto",
                                                              "doc_date": "2026-07-09", "total": 220.0, "handwritten_job_no": "240617", "handwritten_cost_code": "04-100"}), None, None)
    assert matching.match_transactions(conn)["receipt"] == 1   # the still-open PRINCESS AUTO line is re-scanned and now matches
    assert auto_resolve(conn) >= 1
    assert not [i for i in open_items(conn) if i["kind"] == "missing_receipt"]
