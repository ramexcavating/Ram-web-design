"""Canned extractor outputs standing in for what Claude returns on real documents."""
RECEIPT_HOME_HARDWARE = {
    "doc_type": "receipt", "confidence": 0.93, "legible": True, "vendor_name": "Home Hardware Quesnel", "doc_date": "2026-08-18",
    "subtotal": 84.51, "gst": 4.23, "pst": 5.92, "total": 94.66, "payment_method": "Visa", "card_last4": "4321",
    "handwritten_job_no": "240617", "handwritten_cost_code": "04.100", "line_items": [{"description": "Marking paint, zip ties", "amount": 84.51}],
}
RECEIPT_NO_JOB = {
    "doc_type": "receipt", "confidence": 0.9, "legible": True, "vendor_name": "Petro-Canada", "doc_date": "2026-08-19",
    "total": 212.40, "gst": 10.11, "payment_method": "Visa", "handwritten_job_no": None, "handwritten_cost_code": None,
    "line_items": [{"description": "Diesel 148.2L", "amount": 202.29}],
}
INVOICE_BRANDT = {
    "doc_type": "vendor_invoice", "confidence": 0.97, "legible": True, "vendor_name": "Brandt Tractor Ltd.", "invoice_no": "1779280",
    "doc_date": "2026-08-12", "due_date": "2026-09-11", "subtotal": 3120.00, "gst": 156.00, "total": 3276.00,
    "handwritten_equipment_id": "EX-03", "line_items": [{"description": "Hydraulic pump EX-03", "amount": 3120.0, "equipment_id": "EX-03"}],
}
INVOICE_CURBING = {
    "doc_type": "vendor_invoice", "confidence": 0.95, "legible": True, "vendor_name": "Online Curbing", "invoice_no": "OC-2211",
    "doc_date": "2026-08-20", "due_date": "2026-09-02", "total": 38000.00, "gst": 1809.52, "notes": "MDM Kinchant curb and gutter",
}
INVOICE_NO_AMOUNT = {
    "doc_type": "vendor_invoice", "confidence": 0.7, "legible": True, "vendor_name": "Lease Direct", "invoice_no": None, "doc_date": "2026-08-01",
    "total": None, "notes": "portal notification only",
}
TIMESHEET_ED = {
    "doc_type": "timesheet", "confidence": 0.9, "legible": True, "employee_name": "Ed Smith", "period_end": "2026-08-01",
    "time_entries": [
        {"work_date": "2026-07-27", "job_no": "240617", "cost_code": "01-100", "hours": 10, "ot_hours": 2, "description": "MDM"},
        {"work_date": "2026-07-28", "job_no": "240617", "cost_code": "01-100", "hours": 10, "ot_hours": 0, "description": "MDM"},
        {"work_date": "2026-07-29", "job_no": None, "cost_code": None, "hours": 8, "ot_hours": 0, "description": "Dunkley"},
        {"work_date": "2026-07-30", "job_no": None, "cost_code": None, "hours": 8, "ot_hours": 0, "description": "shop"},
    ],
}
CUSTOMER_PAYMENT_IDL = {
    "doc_type": "customer_payment", "confidence": 0.96, "legible": True, "customer_name": "IDL", "doc_date": "2026-08-21", "total": 15120.00,
    "notes": "EFT payment for invoice 600",
}
BANK_STATEMENT_TD = {
    "doc_type": "bank_statement", "confidence": 0.9, "legible": True, "account_hint": "TD Business Chequing ****1234",
    "statement_start": "2026-08-01", "statement_end": "2026-08-31", "opening_balance": 4000.0, "closing_balance": 2650.34,
    "bank_lines": [
        {"txn_date": "2026-08-18", "description": "HOME HARDWARE QUESNEL", "amount": -94.66, "balance": None},
        {"txn_date": "2026-08-05", "description": "MONTHLY ACCOUNT FEE", "amount": -35.00, "balance": None},
        {"txn_date": "2026-08-09", "description": "PRINCESS AUTO", "amount": -220.00, "balance": None},
        {"txn_date": "2026-08-21", "description": "EFT CREDIT IDL", "amount": 15120.00, "balance": 2650.34},
    ],
}
ILLEGIBLE = {"doc_type": "receipt", "confidence": 0.3, "legible": False, "vendor_name": None, "total": None}
