"""The structured-output schema must have no union-typed fields, and string numbers must round-trip."""
import json

from ramfin.extract.schemas import EXTRACTION_SCHEMA
from ramfin.models import Extraction


def _walk(node, path=""):
    if isinstance(node, dict):
        t = node.get("type")
        if isinstance(t, list) or "anyOf" in node or "oneOf" in node:
            yield path
        for k, v in node.items():
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def test_no_union_types():
    assert list(_walk(EXTRACTION_SCHEMA)) == []
    json.dumps(EXTRACTION_SCHEMA)


def test_from_dict_coerces_strings():
    ex = Extraction.from_dict({"doc_type": "receipt", "confidence": "0.9", "legible": True, "vendor_name": "Home Hardware", "total": "$94.66", "gst": "",
                               "subtotal": "84.51", "doc_date": "2026-08-18", "currency": "", "handwritten_job_no": "",
                               "line_items": [{"description": "paint", "quantity": "2", "unit_price": "", "amount": "(12.50)", "equipment_id": ""}],
                               "time_entries": [{"work_date": "2026-07-27", "job_no": "", "cost_code": "", "hours": "10", "ot_hours": "", "equipment_id": "", "description": "MDM"}],
                               "bank_lines": [{"txn_date": "2026-08-18", "description": "x", "amount": "-94.66", "balance": ""}]})
    assert ex.total == 94.66 and ex.gst is None and ex.subtotal == 84.51 and ex.confidence == 0.9 and ex.currency == "CAD"
    assert ex.handwritten_job_no is None
    assert ex.line_items[0].quantity == 2.0 and ex.line_items[0].amount == -12.5 and ex.line_items[0].unit_price is None
    assert ex.time_entries[0].hours == 10.0 and ex.time_entries[0].ot_hours == 0.0 and ex.time_entries[0].job_no is None
    assert ex.bank_lines[0].amount == -94.66 and ex.bank_lines[0].balance is None
