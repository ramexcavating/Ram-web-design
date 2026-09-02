"""JSON schema Claude must return for every document. One call classifies and extracts; the schema keeps it honest."""
from __future__ import annotations

from ..models import DOC_TYPES

_num = {"type": ["number", "null"]}
_str = {"type": ["string", "null"]}

LINE_ITEM = {
    "type": "object",
    "properties": {"description": {"type": "string"}, "quantity": _num, "unit_price": _num, "amount": _num, "equipment_id": _str},
    "required": ["description", "quantity", "unit_price", "amount", "equipment_id"],
    "additionalProperties": False,
}
TIME_ENTRY = {
    "type": "object",
    "properties": {"work_date": {"type": "string"}, "job_no": _str, "cost_code": _str, "hours": {"type": "number"},
                   "ot_hours": {"type": "number"}, "equipment_id": _str, "description": _str},
    "required": ["work_date", "job_no", "cost_code", "hours", "ot_hours", "equipment_id", "description"],
    "additionalProperties": False,
}
BANK_LINE = {
    "type": "object",
    "properties": {"txn_date": {"type": "string"}, "description": {"type": "string"}, "amount": {"type": "number"}, "balance": _num},
    "required": ["txn_date", "description", "amount", "balance"],
    "additionalProperties": False,
}

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string", "enum": list(DOC_TYPES)},
        "confidence": {"type": "number"},
        "legible": {"type": "boolean"},
        "vendor_name": _str,
        "customer_name": _str,
        "invoice_no": _str,
        "doc_date": _str,
        "due_date": _str,
        "subtotal": _num,
        "gst": _num,
        "pst": _num,
        "total": _num,
        "currency": {"type": "string"},
        "payment_method": _str,
        "card_last4": _str,
        "handwritten_job_no": _str,
        "handwritten_cost_code": _str,
        "handwritten_equipment_id": _str,
        "line_items": {"type": "array", "items": LINE_ITEM},
        "employee_name": _str,
        "period_end": _str,
        "time_entries": {"type": "array", "items": TIME_ENTRY},
        "account_hint": _str,
        "statement_start": _str,
        "statement_end": _str,
        "opening_balance": _num,
        "closing_balance": _num,
        "bank_lines": {"type": "array", "items": BANK_LINE},
        "notes": _str,
    },
    "required": ["doc_type", "confidence", "legible", "vendor_name", "customer_name", "invoice_no", "doc_date", "due_date",
                 "subtotal", "gst", "pst", "total", "currency", "payment_method", "card_last4", "handwritten_job_no",
                 "handwritten_cost_code", "handwritten_equipment_id", "line_items", "employee_name", "period_end",
                 "time_entries", "account_hint", "statement_start", "statement_end", "opening_balance", "closing_balance",
                 "bank_lines", "notes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are the document intake clerk for RAM Excavating Limited, a civil construction company in Quesnel, BC, Canada.
You receive one document at a time (a photo of a receipt, a supplier invoice PDF, an employee timesheet, a bank statement,
a customer payment advice, a paystub, a QuickBooks report) and return one JSON object describing it.

Rules:
- Classify honestly. If it is not a financial document, doc_type is "other".
- Dates in ISO format YYYY-MM-DD. Amounts as plain numbers in CAD. total is the grand total including taxes.
- GST in BC is 5%. PST is 7% and only applies to some goods; report it separately if shown.
- RAM writes a JOB NUMBER (six digits, YYMMDD of the estimate, e.g. 240617 for MDM, 241115 for IDL, 260102 for Dunkley)
  and a COST CODE by hand on receipts before photographing them. Transcribe handwriting into handwritten_job_no and
  handwritten_cost_code exactly as written; leave null if absent. Equipment unit IDs look like EX-03, DT-02, SE-01.
- For timesheets: employee_name, period_end, and one time_entries row per day worked with job_no, cost_code, hours and
  ot_hours. If a day shows a job name rather than a number, put the name in description and leave job_no null.
- For bank or card statements: account_hint (institution and last 4 digits), statement period, opening/closing balances,
  and every transaction line with money out as a negative amount.
- For customer payments (EFT advice, remittance): customer_name, total received, and the invoice numbers paid in notes.
- legible=false if key fields (vendor, date, total) cannot be read. confidence reflects how sure you are of doc_type AND
  the key amounts, from 0 to 1.
- Never invent a number. Null beats a guess."""
