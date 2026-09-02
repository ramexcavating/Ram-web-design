# RAM Finance System (ramfin): Architecture

## The one-paragraph version

A single database is the source of truth for every dollar that moves through RAM Excavating. Documents arrive from
wherever they arrive (three Microsoft 365 mailboxes, the old ramcontracting@live.ca mailbox, the CamScanner
upload folder, bank CSV exports). Claude reads each one once, says what it is and what is on it, and the code
does the rest deterministically: files the original to the right SharePoint folder with the right name, writes
the ledger row, matches it against the bank, costs it to a job and cost code, rolls the 13-week forecast, applies
the no-breach rule, and puts anything it cannot decide on a short list for Rodney. The spreadsheets Rodney already
knows become outputs of the database rather than the place the truth lives.

## Why this shape

The Cowork routine proved the workflow. It also showed the limits of running a finance system out of prompts and
Excel files:

- **State lived in workbooks.** Five dated copies of the cash flow tool exist on SharePoint. Which one is right
  depends on which run last wrote it.
- **Runs failed silently.** The Aug 20 run died on an interactive permission prompt and nothing was written. A
  scheduled job with application permissions never prompts.
- **Everything was re-derived every week.** Each run re-read the mailboxes and re-decided what was already decided.
  With a database the system remembers: a receipt coded once stays coded; a vendor's cost code is learned.
- **Money that never hit the ledger.** QuickBooks A/P sat ~$100K short of the register for four weeks. That gap
  closes when the register talks to QuickBooks directly (the API works for Canadian companies even though the
  Claude connector does not).

## Sources in

| Source | How | Notes |
|---|---|---|
| rmickey@, accounts@, emickey@ | Microsoft Graph, application permissions, receivedDateTime watermark per mailbox | Attachments (pdf/jpg/png/heic/xlsx/csv) plus body-only receipts (GoDaddy, Anthropic, Stripe-style). Own automated reports are skipped. |
| ramcontracting@live.ca | IMAP with an app password, or set a forward to accounts@ | Forwarding is simpler and permanent; IMAP is there if forwarding is not wanted. |
| CamScanner | Point CamScanner's auto-upload at a OneDrive/SharePoint folder; the system polls it | Also accepts any local folder (scanner drop folder, USB). Image-only PDFs are fine: Claude reads them visually. |
| Bank statements | CSV export from online banking (preferred) or PDF statement forwarded to accounts@ | Same de-duplication key either way. Balances feed the forecast opening position. |
| QuickBooks Online | Intuit REST API, OAuth2 refresh token | Phase 1 reads open bills and invoices to compute the register-vs-QBO variance. Phase 2 pushes confirmed bills. |
| Rodney | Edits GREEN columns in the review workbook, or replies to the digest | Read back by `ramfin review`. Only changed cells are applied; the system never overwrites a status Rodney set. |

## Pipeline

```
ingest  ──►  documents(status=new)  ──►  process  ──►  ledger rows + filed original
                                              │
                                              ▼
                                   action_items (needs your input)
                                              ▲
reconcile: bank lines ↔ receipts / AP / AR ───┘
                                              │
report: forecast → no-breach → workbook + markdown + digest email
```

Every stage is idempotent. Re-running never duplicates a document (content hash), a bank line (account, date,
description, amount, sequence), an invoice (vendor, invoice number), a timesheet (employee, period end) or an action
item (kind, referenced row).

## The extraction call

One Claude call per document, `claude-opus-5`, structured output constrained by `EXTRACTION_SCHEMA`. The schema
carries a `doc_type` enum and every field any document type could have; irrelevant fields come back null. PDFs are
sent as documents (Claude reads scanned, text-less PDFs), photos as images, spreadsheets as text. The system prompt
is cached. Cost is roughly one to three cents a document at current pricing; a busy month of 300 documents is under
$10.

What the code trusts Claude for: reading. What it never trusts Claude for: deciding. Filing paths, due dates,
cost-code suggestions, matching, forecasting and deferrals are all plain code with tests.

## Data model (SQLite, `data/ramfin.sqlite`)

`documents` (every file ever seen, hash, where it came from, where it went, the raw extraction) →
`receipts`, `ap_invoices`, `ar_invoices`, `timesheets`/`time_entries`, `bank_transactions`/`bank_balances`,
`payroll_runs`. Reference: `vendors` (aliases, default terms, category, critical flag), `jobs` (YYMMDD numbers,
project folder), `cost_codes` (the 825-code list), `employees`, `debts`, `recurring`. Control: `action_items`,
`scan_log`, `sync_state`.

SQLite is deliberate. One file, no server, trivially backed up to SharePoint, fast enough for a company this size
for a decade. If RAM grows to the point where several people write to it at once, the schema ports to Postgres
unchanged.

## Filing rules

Same conventions the current tools established, so nothing already filed is orphaned:

- receipts `06_RECEIPTS/<YYYY>/<YYYY-MM>/yymmdd_VENDOR_amount_job.ext`
- vendor invoices `05_AP_INVOICES/<YYYY-MM>/yymmdd_VENDOR_INV<no>.ext`; statements in a `STATEMENTS` subfolder
- timesheets `04_PAYROLL/01_TIMESHEETS/<YYYY>/PP_<period end>/<period end>_EMPLOYEE_Timesheet.ext`
- bank statements `07_BANK_STATEMENTS/<account>/<YYYY>/`
- QuickBooks reports `02_RAM_FINANCIAL_UPDATES/yymmdd_<original>`
- customer payment advices into the project's `05.1 Acct & Billing/5.1.02 Progress Claims/02_EFT_RECEIPTS`
- anything unreadable `06_RECEIPTS/00_UNFILED_NEEDS_REVIEW/`, with an action item

## Cost coding

Priority order: the code written by hand on the receipt (if it exists in the standard list) → the vendor's most
frequent code in history → the vendor default → a keyword hint. Anything under 50% confidence is left blank and
turns yellow in the review workbook. Every code Rodney fills in teaches the next suggestion.

## Bank reconciliation

Each statement line is categorised (fee, interest, transfer, card payment, loan, CRA, payroll, insurance, deposit,
purchase) and matched: purchases to receipts (amount to the cent within 7 days) or vendor invoices (amount and
vendor within 45 days); deposits to open receivables (exact balance, or a customer's whole open set). A purchase with
nothing behind it is a MISSING RECEIPT action item and drives the capture rate on the dashboard. CRA retention rules
from the existing AP register README still apply; the images are the record.

## Forecast and the floor

Thirteen Monday-to-Sunday weeks. Opening position = chequing cash minus operating line drawn (`forecast.basis`).
Inflows: open receivables at their expected date, recurring inflows (the ~$24K/month consulting engagement belongs in
`recurring`). Outflows: payables at their planned pay date, projected payroll runs from the anchor pay date, CRA
remittances on the 15th, debt payments, recurring outflows. Items with no planned pay date are reported as
invisible rather than silently omitted.

**The floor needs a decision.** Procedure RAM-10-PR-10 speaks of a $60K minimum. The current workbook grades a week
OK when the position closes above zero, which is the same thing as saying the $60K line must not be exceeded.
`forecast.floor_amount` defaults to 0 on the position basis to match the workbook's behaviour. Setting it to 60000
means "never touch the line", which today would put every week in breach. Pick one and write it into config.

**No-breach rule.** For each breaching week, the largest discretionary payable moves to the first later week that
stays above the floor. Payroll, CRA, debt minimums, WorkSafeBC and vendors flagged critical are never moved. Every
move is recorded (original date kept), flagged orange, and raised as a priority-1 action item to confirm with the
supplier in writing.

## Outputs

- `yymmdd_RAM_WEEKLY_REVIEW.xlsx`: DASHBOARD, FORECAST_13WK, AP_TRACKER, AR_TRACKER, RECEIPTS, MISSING_RECEIPTS,
  JOB_COST, TIMESHEETS, ACTIONS. Green headers are editable and read back.
- `yymmdd_RAM_Weekly_Cashflow_Report.md`: the narrative report, filed to `01_WEEKLY_MANAGERS_REPORT`.
- Digest email: what changed, what moved, what needs an answer, one line each, priority-ordered.

## Security

Secrets live in environment variables or GitHub Actions secrets, never in the repo or the config file. The Graph
app has read on mail, send on the accounts mailbox, and read/write on the two SharePoint sites; nothing more. The
database contains financial data: keep the `data/` folder out of git (it is), and store the SharePoint copy in the
finance library with the same permissions as the cash flow tool.
