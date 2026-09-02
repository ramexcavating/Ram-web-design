"""Typed view of what the extractor returns. Mirrors extract/schemas.py; keep both in step."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DOC_TYPES = (
    "receipt",            # till slip / card receipt / online order confirmation - money already spent
    "vendor_invoice",     # supplier or subcontractor invoice - money owed
    "vendor_statement",   # supplier account statement
    "customer_payment",   # EFT advice / remittance from a client - money received
    "customer_invoice",   # RAM's own invoice to a client (copy)
    "timesheet",          # employee weekly timesheet
    "paystub",            # payroll output from ACG
    "bank_statement",     # RBC / TD / Capital One statement
    "qbo_report",         # QuickBooks report export
    "cra_notice",         # CRA / WorkSafeBC / PST correspondence
    "other",
)


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("$", "").replace(",", "").replace("CAD", "").strip()
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = s.strip("()-").strip()
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


@dataclass
class LineItem:
    description: str = ""
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None
    equipment_id: str | None = None


@dataclass
class TimeEntry:
    work_date: str = ""
    job_no: str | None = None
    cost_code: str | None = None
    hours: float = 0.0
    ot_hours: float = 0.0
    equipment_id: str | None = None
    description: str | None = None


@dataclass
class BankLine:
    txn_date: str = ""
    description: str = ""
    amount: float = 0.0
    balance: float | None = None


@dataclass
class Extraction:
    doc_type: str = "other"
    confidence: float = 0.0
    legible: bool = True
    vendor_name: str | None = None
    customer_name: str | None = None
    invoice_no: str | None = None
    doc_date: str | None = None
    due_date: str | None = None
    subtotal: float | None = None
    gst: float | None = None
    pst: float | None = None
    total: float | None = None
    currency: str = "CAD"
    payment_method: str | None = None
    card_last4: str | None = None
    handwritten_job_no: str | None = None
    handwritten_cost_code: str | None = None
    handwritten_equipment_id: str | None = None
    line_items: list[LineItem] = field(default_factory=list)
    employee_name: str | None = None
    period_end: str | None = None
    time_entries: list[TimeEntry] = field(default_factory=list)
    account_hint: str | None = None
    statement_start: str | None = None
    statement_end: str | None = None
    opening_balance: float | None = None
    closing_balance: float | None = None
    bank_lines: list[BankLine] = field(default_factory=list)
    notes: str | None = None

    NUMERIC = {"subtotal", "gst", "pst", "total", "opening_balance", "closing_balance", "confidence"}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Extraction":
        d = dict(d or {})

        def coerce(obj: dict, numeric: set[str], required_num: set[str] = frozenset()) -> dict:
            out = {}
            for k, v in obj.items():
                if isinstance(v, str) and v.strip() == "":
                    v = 0.0 if k in required_num else None
                elif k in numeric and isinstance(v, str):
                    v = _to_float(v)
                    if v is None and k in required_num:
                        v = 0.0
                out[k] = v
            return out

        li = [LineItem(**{k: v for k, v in coerce(x, {"quantity", "unit_price", "amount"}).items() if k in LineItem.__dataclass_fields__}) for x in d.pop("line_items", []) or []]
        te = [TimeEntry(**{k: v for k, v in coerce(x, {"hours", "ot_hours"}, {"hours", "ot_hours"}).items() if k in TimeEntry.__dataclass_fields__}) for x in d.pop("time_entries", []) or []]
        bl = [BankLine(**{k: v for k, v in coerce(x, {"amount", "balance"}, {"amount"}).items() if k in BankLine.__dataclass_fields__}) for x in d.pop("bank_lines", []) or []]
        known = coerce({k: v for k, v in d.items() if k in cls.__dataclass_fields__}, cls.NUMERIC, {"confidence"})
        if known.get("currency") is None:
            known["currency"] = "CAD"
        if known.get("legible") is None:
            known["legible"] = True
        obj = cls(**known)
        obj.line_items, obj.time_entries, obj.bank_lines = li, te, bl
        if obj.doc_type not in DOC_TYPES:
            obj.doc_type = "other"
        return obj

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)
