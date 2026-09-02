# Setup

## 1. Python

```
cd finance
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -q
cp config/config.example.yaml config/config.yaml
cp .env.example .env
```

Optional for HEIC photos from iPhones: `pip install pillow pillow-heif`.

## 2. Microsoft Graph (mail + SharePoint)

Entra admin centre → App registrations → New registration ("RAM Finance Automation", single tenant).
- Supported account types: any organizational directory AND personal Microsoft accounts (for the old mailbox).
- Authentication → Allow public client flows: Yes (device-code sign-in for the old mailbox).
- Certificates & secrets → new client secret (24 months). Record it once; it is not shown again.
- API permissions → Microsoft Graph → **Application** permissions: `Mail.Read`, `Mail.Send`, `Sites.Selected`
  (preferred) or `Sites.ReadWrite.All`. Grant admin consent.
- With `Sites.Selected`, grant the app write on the BUSINESSEXECUTIVE and PROJECTS sites (Graph
  `POST /sites/{id}/permissions`) so it cannot touch other sites.
- Restrict mailbox access to the three mailboxes with an Exchange application access policy:
  `New-ApplicationAccessPolicy -AppId <client id> -PolicyScopeGroupId <mail-enabled group> -AccessRight RestrictAccess`.

Set `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`.

## 3. Old mailbox (ramcontracting@live.ca)

Read in place, nothing forwarded. The app registration must allow personal Microsoft accounts and public client
flows (GETTING_STARTED.md step 1). Then once: `ramfin auth legacy`, enter the printed code at the printed URL, sign
in as the old address. The token cache is stored with the database (`ramfin db push`). IMAP with a password is no
longer accepted by Outlook.com; the `legacy_imap` block stays only for a mailbox on a provider that still allows it.

## 4. CamScanner

In CamScanner: Settings → Auto upload → OneDrive → choose a folder that syncs to
`BUSINESS_EXEC/01_BUSINESS_FINANCE/09_REPORTING/06_RECEIPTS/01_CAMSCANNER_INBOX` (or any folder; set
`sources.camscanner_folder`). Turn on "Recognize text" so the PDFs carry a text layer; the system reads image-only
PDFs too, it is just slower.

## 5. QuickBooks Online

developer.intuit.com → create an app → Production keys. Run the OAuth2 authorisation once to obtain a refresh
token for the RAM company file (the Intuit OAuth Playground does this in a browser). Set `QBO_CLIENT_ID`,
`QBO_CLIENT_SECRET`, `QBO_REFRESH_TOKEN`, `QBO_REALM_ID`. Intuit rotates refresh tokens every 100 days; the client
stores the new one in memory and `ramfin` prints it to the log when it changes, so update the secret when told.

## 6. Anthropic

`ANTHROPIC_API_KEY` from console.anthropic.com. Model is set in config (`claude-opus-5`).

## 7. Reference data

- `config/cost_codes.csv` with columns `code,description,category`: export the COST_CODES tab of RAM_AP_REGISTER.xlsx.
- `config/vendors.csv` with `name,aliases,email_domain,default_cost_code,default_terms_days,category,critical`.
  Aliases pipe-separated. `critical=1` means never deferred.
- Jobs in `config.yaml`:
  ```yaml
  jobs:
    - {job_no: "240617", name: MDM Kinchant, client: MDM Construction, sharepoint_folder: 01_ACTIVE_PROJECTS/240617_MDM_KINCHANT}
    - {job_no: "241115", name: IDL Consulting, client: IDL, sharepoint_folder: 01_ACTIVE_PROJECTS/241115_IDL_CONSULTING_2024-2025}
  ```
- Debts, recurring items and employee rates: insert directly for now (`sqlite3 data/ramfin.sqlite`) or via the
  small seed script you will find easiest; a `ramfin seed` command is on the Phase 1 list.

```
ramfin init
ramfin balance rbc_chq 17782.00 --as-of 2026-08-31
ramfin balance td_loc 57812.00 --as-of 2026-08-31
ramfin ingest && ramfin process && ramfin reconcile && ramfin weekly
ramfin inbox -v
```

## 8. Scheduling

**GitHub Actions** (already in `.github/workflows/ramfin.yml`): add the secrets above plus `RAMFIN_CONFIG_B64`
(`base64 -w0 config/config.yaml`). Weekday 06:30 Pacific digest run, Monday 05:30 full report. The database is
pulled from and pushed to SharePoint (`03_CASHFLOW_TRACKING/_ramfin`) around every run.

**Office PC** (alternative): Task Scheduler → weekday 06:30 → `ramfin run-all --send`. The database then lives on
that PC's `finance/data`, synced by OneDrive if the repo is inside a synced folder.

## 9. First run checklist

- [ ] `ramfin process --dry-run --local` on a folder of ten known receipts: are the filenames right?
- [ ] First real `ramfin process` on 30 documents: review the RECEIPTS and AP_TRACKER tabs, correct, `ramfin review`.
- [ ] Balances entered for RBC, TD chequing, TD line.
- [ ] Decide `forecast.floor_amount` and write it down in RAM-10-PR-10 as well.
- [ ] Compare the first weekly report to the current cash flow tool line by line before trusting it.
