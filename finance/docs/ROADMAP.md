# Roadmap

Each phase is usable on its own. Nothing later depends on skipping something earlier.

## Phase 0: this commit

- Package, schema, config, tests. Deterministic core (filing, cost codes, matching, forecast, no-breach, job cost,
  timesheets, payroll accrual, review workbook, read-back, digest).
- Connectors written for Graph mail/SharePoint, IMAP, folders, bank CSV (RBC, TD, Capital One), QuickBooks read.
- Scheduler workflow for GitHub Actions.
- Offline end-to-end test proves the loop: drop folder → extraction → ledger → filing → forecast → workbook → edits back.

## Phase 1: turn it on (first two weeks)

1. Entra app registration and QuickBooks developer app (SETUP.md). Put secrets in GitHub or on the office PC.
2. Export the 825 cost codes and the current vendor list to `config/cost_codes.csv` and `config/vendors.csv`.
   Mark critical vendors (Four Rivers fuel, ACG, lenders, CRA, WorkSafeBC).
3. Seed: jobs (with SharePoint folders), debts (Community Futures, CWB, CEBA, Lending Loop, property tax), recurring
   (consulting engagement in, insurance out), employee base rates, current bank balances.
4. Backfill: run `ramfin ingest` with a 90-day lookback and `ramfin process`. Review the first workbook carefully;
   correct codes and vendors; the system learns from it.
5. Decide the floor (ARCHITECTURE.md, "The floor"). Turn on the schedule.
6. Retire the Monday Cowork cash flow update once two consecutive weekly reports reconcile to it.

## Phase 2: close the QuickBooks gap (weeks 3 to 6)

- Push confirmed vendor bills to QuickBooks with job (Class) and cost code (Account) so the bookkeeper stops
  re-keying and A/P is never four weeks behind again.
- Pull QuickBooks payments and deposits back so `Paid` flows both ways.
- Nightly variance check as a hard gate: if register and QuickBooks differ by more than $1,000, priority-1 item.

## Phase 3: billing and WIP (weeks 6 to 10)

- Progress claim generator per job: costs to date by cost code vs estimate, percent complete, holdback, GST.
- Holdback diary: 55-day release dates from substantial completion, invoiced automatically when due.
- WIP schedule for the lender and surety packages, produced from the same tables the weekly report uses.

## Phase 4: payroll and timecards at the source

- A phone-friendly timecard form (job, cost code, hours, equipment) so field entries skip the paper step. The PDF
  route stays for anyone who prefers it.
- Payroll export in the format ACG wants; the CRA remittance figure in the forecast becomes actual, not estimated.
- WorkSafeBC assessable payroll tracking against CU 721031.

## Phase 5: equipment economics

- Fold the Equipment Maintenance Log routine into the same database: repairs and fuel coded to a unit ID roll up
  to owning-and-operating cost per hour per machine, fed back to the cost library and bid rates.

## Things this system deliberately does not do

- Replace QuickBooks or the external accountant. It feeds them and checks them.
- Pay anything. It schedules and recommends; a human moves money.
- Make judgement calls. Anything with two reasonable answers becomes an action item.
