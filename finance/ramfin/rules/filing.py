"""Where a document goes and what it is called. Mirrors the conventions already in use on SharePoint:

  receipts        06_RECEIPTS/<YYYY>/<YYYY-MM>/yymmdd_VENDOR_amount_job.ext
  vendor invoices 05_AP_INVOICES/<YYYY-MM>/yymmdd_VENDOR_INV<no>.ext
  statements      05_AP_INVOICES/<YYYY-MM>/STATEMENTS/yymmdd_VENDOR_STATEMENT.ext
  timesheets      04_PAYROLL/01_TIMESHEETS/<YYYY>/PP_<period end>/<period end>_EMPLOYEE_Timesheet.ext
  bank statements 07_BANK_STATEMENTS/<account>/<YYYY>/yymmdd_ACCOUNT_STATEMENT.ext
  QBO reports     02_RAM_FINANCIAL_UPDATES/yymmdd_<original>.ext
  customer pay    PROJECTS/<job folder>/05.1 Acct & Billing/5.1.02 Progress Claims/02_EFT_RECEIPTS/yymmdd_CUSTOMER_EFT_amount.ext
  unreadable      06_RECEIPTS/00_UNFILED_NEEDS_REVIEW/yymmdd_<original>.ext
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

from ..models import Extraction


@dataclass
class FilingDecision:
    folder: str          # path relative to the library root (or projects library for customer payments)
    filename: str
    library: str = "finance"   # finance | projects
    needs_review: bool = False
    reason: str = ""


def slug(text: str | None, maxlen: int = 28) -> str:
    if not text:
        return "UNKNOWN"
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"\b(inc|ltd|limited|corp|co|llc|the)\b\.?", "", t, flags=re.I)
    t = re.sub(r"[^A-Za-z0-9]+", "", t).upper()
    return (t or "UNKNOWN")[:maxlen]


def yymmdd(d: str | date | None, fallback: date | None = None) -> str:
    dd = parse_date(d) or fallback or date.today()
    return dd.strftime("%y%m%d")


def parse_date(v: str | date | datetime | None) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d-%b-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s[:20], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def money_token(amount: float | None) -> str:
    if amount is None:
        return "0"
    return f"{amount:.2f}".replace(".", "-")


def ext_of(filename: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]{2,5})$", filename or "")
    return m.group(1).lower() if m else "pdf"


def decide(ex: Extraction, original_filename: str, sp: dict[str, str], received: date | None = None, job_folder: str | None = None) -> FilingDecision:
    ext = ext_of(original_filename)
    d = parse_date(ex.doc_date) or received or date.today()
    ym = d.strftime("%Y-%m")
    y = d.strftime("%Y")
    stamp = d.strftime("%y%m%d")

    if not ex.legible or ex.confidence < 0.5 or ex.doc_type == "other":
        return FilingDecision(sp["unfiled"], f"{stamp}_{slug(original_filename.rsplit('.',1)[0], 40)}.{ext}", needs_review=True,
                              reason="illegible or unrecognised" if not ex.legible or ex.doc_type == "other" else "low confidence")

    if ex.doc_type == "receipt":
        job = ex.handwritten_job_no or "NOJOB"
        name = f"{stamp}_{slug(ex.vendor_name)}_{money_token(ex.total)}_{job}.{ext}"
        return FilingDecision(f"{sp['receipts']}/{y}/{ym}", name, needs_review=not ex.handwritten_job_no,
                              reason="" if ex.handwritten_job_no else "no job number on receipt")

    if ex.doc_type == "vendor_invoice":
        inv = re.sub(r"[^A-Za-z0-9-]", "", ex.invoice_no or "NOINV")
        return FilingDecision(f"{sp['ap_invoices']}/{ym}", f"{stamp}_{slug(ex.vendor_name)}_INV{inv}.{ext}")

    if ex.doc_type == "vendor_statement":
        return FilingDecision(f"{sp['ap_invoices']}/{ym}/STATEMENTS", f"{stamp}_{slug(ex.vendor_name)}_STATEMENT.{ext}")

    if ex.doc_type == "timesheet":
        pe = parse_date(ex.period_end) or d
        return FilingDecision(f"{sp['timesheets']}/{pe.strftime('%Y')}/PP_{pe.isoformat()}",
                              f"{pe.isoformat()}_{slug(ex.employee_name, 30)}_Timesheet.{ext}")

    if ex.doc_type == "paystub":
        pe = parse_date(ex.period_end) or d
        return FilingDecision(f"{sp['timesheets']}/{pe.strftime('%Y')}/PP_{pe.isoformat()}/PAYSTUBS",
                              f"{pe.isoformat()}_{slug(ex.employee_name, 30)}_Paystub.{ext}")

    if ex.doc_type == "bank_statement":
        acct = slug(ex.account_hint, 20)
        end = parse_date(ex.statement_end) or d
        return FilingDecision(f"{sp['bank_statements']}/{acct}/{end.strftime('%Y')}", f"{end.strftime('%y%m%d')}_{acct}_STATEMENT.{ext}")

    if ex.doc_type == "qbo_report":
        base = re.sub(r"^\d{6}_", "", original_filename.rsplit(".", 1)[0])
        return FilingDecision(sp["qb_reports"], f"{stamp}_{slug(base, 50)}.{ext}")

    if ex.doc_type == "customer_payment":
        name = f"{stamp}_{slug(ex.customer_name)}_EFT_{money_token(ex.total)}.{ext}"
        if job_folder:
            return FilingDecision(f"{job_folder}/05.1 Acct & Billing/5.1.02 Progress Claims/02_EFT_RECEIPTS", name, library="projects")
        return FilingDecision(f"{sp['finance_root']}/08_AR_RECEIPTS/{ym}", name, needs_review=True, reason="no project folder matched")

    if ex.doc_type == "customer_invoice":
        inv = re.sub(r"[^A-Za-z0-9-]", "", ex.invoice_no or "NOINV")
        return FilingDecision(f"{sp['finance_root']}/08_AR_INVOICES/{ym}", f"{stamp}_{slug(ex.customer_name)}_INV{inv}.{ext}")

    if ex.doc_type == "cra_notice":
        return FilingDecision(f"{sp['finance_root']}/10_CRA_WSBC/{y}", f"{stamp}_{slug(original_filename.rsplit('.',1)[0], 40)}.{ext}")

    return FilingDecision(sp["unfiled"], f"{stamp}_{slug(original_filename, 40)}.{ext}", needs_review=True, reason="unhandled type")
