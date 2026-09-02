from datetime import date

from ramfin.models import Extraction
from ramfin.rules import filing
from tests.fixtures import extractions as fx

SP = {"receipts": "R", "ap_invoices": "AP", "timesheets": "TS", "bank_statements": "BK", "qb_reports": "QB", "unfiled": "UNF", "finance_root": "FIN"}


def test_receipt_naming_matches_convention():
    d = filing.decide(Extraction.from_dict(fx.RECEIPT_HOME_HARDWARE), "IMG_1735.jpeg", SP)
    assert d.folder == "R/2026/2026-08"
    assert d.filename == "260818_HOMEHARDWAREQUESNEL_94-66_240617.jpeg"
    assert not d.needs_review


def test_receipt_without_job_flags_review():
    d = filing.decide(Extraction.from_dict(fx.RECEIPT_NO_JOB), "scan.pdf", SP)
    assert d.needs_review and "NOJOB" in d.filename


def test_invoice_and_statement_paths():
    d = filing.decide(Extraction.from_dict(fx.INVOICE_BRANDT), "invoice.pdf", SP)
    assert d.folder == "AP/2026-08" and d.filename == "260812_BRANDTTRACTOR_INV1779280.pdf"
    s = filing.decide(Extraction.from_dict({**fx.INVOICE_BRANDT, "doc_type": "vendor_statement"}), "stmt.pdf", SP)
    assert s.folder.endswith("/STATEMENTS")


def test_timesheet_path_uses_period_end():
    d = filing.decide(Extraction.from_dict(fx.TIMESHEET_ED), "2026-08-01_ED_SMITH_Employee_Timesheet (1).pdf", SP)
    assert d.folder == "TS/2026/PP_2026-08-01" and d.filename == "2026-08-01_EDSMITH_Timesheet.pdf"


def test_illegible_goes_to_unfiled():
    d = filing.decide(Extraction.from_dict(fx.ILLEGIBLE), "blurry.jpg", SP, received=date(2026, 8, 20))
    assert d.folder == "UNF" and d.needs_review and d.filename.startswith("260820_")


def test_customer_payment_into_project_folder():
    d = filing.decide(Extraction.from_dict(fx.CUSTOMER_PAYMENT_IDL), "advice.pdf", SP, job_folder="01_ACTIVE_PROJECTS/241115_IDL")
    assert d.library == "projects" and "02_EFT_RECEIPTS" in d.folder and d.filename == "260821_IDL_EFT_15120-00.pdf"


def test_parse_date_variants():
    assert filing.parse_date("Aug 18, 2026") == date(2026, 8, 18)
    assert filing.parse_date("18/08/2026") == date(2026, 8, 18)
    assert filing.parse_date("2026-08-18T10:00:00Z") == date(2026, 8, 18)
    assert filing.parse_date("garbage") is None
