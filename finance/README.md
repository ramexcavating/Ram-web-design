# ramfin: RAM Excavating financial operations

Receipts, vendor invoices, customer invoices and payments, bank reconciliation, timesheets, payroll accrual, job
cost by cost code, and a 13-week cash flow forecast with the no-breach rule, from one database, on a schedule,
with a short daily list of what needs a human.

- `docs/GETTING_STARTED.md`: the plain-English sequence, who does what
- `docs/ARCHITECTURE.md`: how it works and why it is shaped this way
- `docs/SETUP.md`: credentials, reference data, scheduling, first-run checklist
- `docs/ROADMAP.md`: phases from "turn it on" through QuickBooks sync, WIP, payroll at the source, equipment

```
pip install -e ".[dev]" && python -m pytest -q
ramfin --help
```

Layout:

```
ramfin/
  config.py        settings (YAML + env)
  db.py            SQLite schema and helpers
  models.py        Extraction dataclass (what Claude returns)
  filer.py         LocalFiler / SharePointFiler
  pipeline.py      ingest -> process -> reconcile -> weekly
  cli.py           ramfin command line
  sources/         graph (mail + SharePoint), mailbox, legacy_imap, folder, bank_import, qbo
  extract/         schemas, ocr (content blocks), extractor (Claude, structured output)
  rules/           filing, cost_codes, vendors, matching, forecast (+ no-breach)
  ledger/          intake (extraction -> rows), timesheets, jobcost
  reports/         weekly (report content), export_xlsx (review workbook), import_decisions (read-back)
  notify/          inbox (action items, digest), mailer
tests/             offline; FakeExtractor stands in for Claude
```
