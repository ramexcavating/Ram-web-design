"""SQLite persistence. One file, one source of truth. Spreadsheets are exports of this, not the other way round."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,               -- mailbox:<address> | imap:<address> | camscanner | folder | manual
    source_ref TEXT,                    -- message id / file id
    sender TEXT,
    subject TEXT,
    filename TEXT NOT NULL,
    mime TEXT,
    local_path TEXT,
    received_at TEXT,
    doc_type TEXT DEFAULT 'unclassified',
    status TEXT NOT NULL DEFAULT 'new', -- new | extracted | filed | needs_review | ignored | error
    filed_path TEXT,
    extracted_json TEXT,
    confidence REAL,
    legible INTEGER DEFAULT 1,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL UNIQUE,
    aliases TEXT DEFAULT '',
    email_domain TEXT,
    default_cost_code TEXT,
    default_terms_days INTEGER DEFAULT 30,
    category TEXT DEFAULT 'supplier',   -- supplier | sub | fuel | lease | payroll | cra | debt | utility | professional
    critical INTEGER DEFAULT 0,         -- 1 = never defer under the no-breach rule
    qbo_id TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    job_no TEXT PRIMARY KEY,            -- YYMMDD the job was first estimated (RAM convention)
    name TEXT NOT NULL,
    client TEXT,
    status TEXT DEFAULT 'active',
    contract_value REAL,
    sharepoint_folder TEXT
);

CREATE TABLE IF NOT EXISTS cost_codes (
    code TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    category TEXT
);

CREATE TABLE IF NOT EXISTS ap_invoices (
    id INTEGER PRIMARY KEY,
    vendor_id INTEGER REFERENCES vendors(id),
    invoice_no TEXT,
    invoice_date TEXT,
    due_date TEXT,
    amount REAL,
    gst REAL,
    amount_confirmed INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Unpaid', -- Unpaid|Scheduled|Partially Paid|Paid|Deferred (no-breach)|Disputed|On Hold|Void-Credit|Reference only
    planned_pay_date TEXT,
    original_planned_pay_date TEXT,
    paid_date TEXT,
    method TEXT,
    job_no TEXT REFERENCES jobs(job_no),
    cost_code TEXT,
    document_id INTEGER REFERENCES documents(id),
    category TEXT DEFAULT 'supplier',
    notes TEXT,
    qbo_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(vendor_id, invoice_no)
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY,
    vendor_id INTEGER REFERENCES vendors(id),
    receipt_date TEXT,
    amount REAL,
    gst REAL,
    payment_method TEXT,
    card_last4 TEXT,
    job_no TEXT,
    cost_code TEXT,
    equipment_id TEXT,
    document_id INTEGER REFERENCES documents(id),
    reimbursable INTEGER DEFAULT 0,
    reimbursed INTEGER DEFAULT 0,
    legible INTEGER DEFAULT 1,
    matched_txn_id INTEGER,
    description TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ar_invoices (
    id INTEGER PRIMARY KEY,
    customer TEXT NOT NULL,
    invoice_no TEXT,
    invoice_date TEXT,
    due_date TEXT,
    amount REAL NOT NULL,
    holdback REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Open',   -- Open | Paid | Partially Paid | Doubtful | Estimate
    expected_date TEXT,
    paid_date TEXT,
    paid_amount REAL DEFAULT 0,
    job_no TEXT REFERENCES jobs(job_no),
    document_id INTEGER REFERENCES documents(id),
    holdback_release_date TEXT,
    notes TEXT,
    qbo_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(customer, invoice_no)
);

CREATE TABLE IF NOT EXISTS bank_transactions (
    id INTEGER PRIMARY KEY,
    account_key TEXT NOT NULL,
    txn_date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,               -- negative = money out
    balance REAL,
    seq INTEGER DEFAULT 0,
    category TEXT,                      -- purchase | fee | interest | transfer | card_payment | loan | cra | payroll | deposit | customer_payment | other
    receipt_required INTEGER DEFAULT 1,
    match_type TEXT,                    -- receipt | ap | ar | rule | none
    match_id INTEGER,
    statement_ref TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(account_key, txn_date, description, amount, seq)
);

CREATE TABLE IF NOT EXISTS bank_balances (
    id INTEGER PRIMARY KEY,
    as_of TEXT NOT NULL,
    account_key TEXT NOT NULL,
    balance REAL NOT NULL,              -- for LOC: amount drawn (positive)
    source TEXT NOT NULL,               -- statement | csv | manual | online_banking
    created_at TEXT NOT NULL,
    UNIQUE(as_of, account_key, source)
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    position TEXT,
    base_rate REAL,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS timesheets (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    period_end TEXT NOT NULL,
    document_id INTEGER REFERENCES documents(id),
    total_hours REAL,
    total_ot_hours REAL DEFAULT 0,
    status TEXT DEFAULT 'received',     -- received | validated | sent_to_payroll | paid
    filed_path TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(employee_id, period_end)
);

CREATE TABLE IF NOT EXISTS time_entries (
    id INTEGER PRIMARY KEY,
    timesheet_id INTEGER REFERENCES timesheets(id) ON DELETE CASCADE,
    work_date TEXT NOT NULL,
    job_no TEXT,
    cost_code TEXT,
    hours REAL NOT NULL DEFAULT 0,
    ot_hours REAL NOT NULL DEFAULT 0,
    equipment_id TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id INTEGER PRIMARY KEY,
    period_end TEXT NOT NULL UNIQUE,
    pay_date TEXT NOT NULL,
    gross REAL,
    source_deductions REAL,
    net REAL,
    cra_remit_due TEXT,
    status TEXT DEFAULT 'projected',    -- projected | submitted | paid
    notes TEXT
);

CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT,                          -- loan | lease | card | tax | loc
    balance REAL,
    monthly_payment REAL,
    payment_day INTEGER,
    annual_rate REAL,
    critical INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS recurring (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    amount REAL NOT NULL,
    direction TEXT NOT NULL,            -- in | out
    cadence TEXT NOT NULL,              -- weekly | biweekly | monthly
    next_date TEXT NOT NULL,
    category TEXT,
    critical INTEGER DEFAULT 0,
    end_date TEXT
);

CREATE TABLE IF NOT EXISTS equipment (
    unit_id TEXT PRIMARY KEY,           -- EX-03, DT-02, SE-01
    description TEXT,
    make_model TEXT,
    sharepoint_folder TEXT,             -- 05_EQUIPMENT/01_FLEET/EX-03 ; receipts copy into <folder>/01_SERVICE_RECORDS
    meter_hours REAL,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS action_items (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,                 -- missing_receipt | uncoded_receipt | unconfirmed_amount | no_pay_date | deferral_to_confirm | illegible | unmatched_deposit | timesheet_issue | qbo_variance | statement_stale | decision
    title TEXT NOT NULL,
    detail TEXT,
    ref_table TEXT,
    ref_id INTEGER,
    priority INTEGER NOT NULL DEFAULT 2, -- 1 = today, 2 = this week, 3 = when convenient
    status TEXT NOT NULL DEFAULT 'open', -- open | resolved | dismissed
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    UNIQUE(kind, ref_table, ref_id)
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY,
    run_at TEXT NOT NULL,
    stage TEXT NOT NULL,
    source TEXT,
    found INTEGER DEFAULT 0,
    new INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS ix_docs_status ON documents(status);
CREATE INDEX IF NOT EXISTS ix_ap_status ON ap_invoices(status, planned_pay_date);
CREATE INDEX IF NOT EXISTS ix_ar_status ON ar_invoices(status, expected_date);
CREATE INDEX IF NOT EXISTS ix_txn_match ON bank_transactions(match_type, txn_date);
CREATE INDEX IF NOT EXISTS ix_actions_open ON action_items(status, priority);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def get_state(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_state(key,value,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, now_iso()),
    )
    conn.commit()


def insert(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> int:
    cols = ", ".join(row.keys())
    qs = ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", tuple(row.values()))
    return int(cur.lastrowid)


def upsert_ignore(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> int | None:
    cols = ", ".join(row.keys())
    qs = ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({qs})", tuple(row.values()))
    return int(cur.lastrowid) if cur.rowcount else None


def rows(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def log_scan(conn: sqlite3.Connection, stage: str, source: str | None, found: int, new: int, errors: int, notes: str = "") -> None:
    insert(conn, "scan_log", dict(run_at=now_iso(), stage=stage, source=source, found=found, new=new, errors=errors, notes=notes))
    conn.commit()
