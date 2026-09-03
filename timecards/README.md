# RAM Timecard — phone timecards for the crews

A timecard app employees open on their phone, fill in at the end of the shift, and send with one tap. Each line is a
**job + cost code**, with the employee's **labour hours (Reg / OT / DT)** and, on the same line, the **equipment unit
and hours** they ran on that cost code, plus a **description**. LOA, own-truck (P/U) and travel km match the current
paper weekly timesheet, so payroll loses nothing and job costing gains the split it never had.

```
timecards/
  app/                 the app itself: static files, no server, no login, works offline
    index.html  app.js  styles.css  sw.js  manifest.webmanifest  icons/
    data/reference.json   jobs, cost codes, equipment: what the pickers show
  data/                the source lists the reference file is built from (CSV, exported from SharePoint)
  tools/build_reference.py   rebuilds app/data/reference.json from the CSVs
```

The finance system reads the cards: `finance/ramfin` (module `ramfin/ledger/timecards.py`) recognises a card in the
accounts mailbox and writes it straight into the `timesheets` / `time_entries` tables, no Claude call, no retyping.

## Website page or a phone app? Both, and this is the answer

You asked whether to attach this to the website or make a phone application you can hand out at onboarding. The right
shape is a **Progressive Web App (PWA)**: a web page that installs to the phone's home screen, opens full-screen like
an app, and keeps working with no signal. There is nothing to publish to the App Store or Google Play, nothing to
sideload, and no per-user licence. Onboarding a new hire is: text them the link, they tap "Add to Home Screen", they
type their name once. Their cards live on their phone until they send them.

Why not the alternatives:

- **A form on ramexcavating.ca (GoDaddy/Wix builder).** Website builders cannot do the searchable 826-code picker, the
  per-line equipment split or offline drafts, and every submission would land as a generic form email you would still
  have to retype. The website *should* link to the app from the Employee Resources page, nothing more.
- **A native iOS/Android app.** Developer accounts ($99 US/yr Apple, $25 Google), store review on every change, and a
  build toolchain to maintain. For five to fifteen crew it buys nothing the PWA does not already do.
- **A Microsoft Form / Power Automate flow.** Would need every employee to have an M365 licence (they do not), and a
  Form cannot do the cost-code picker.
- **A paid timekeeping app (busybusy, Rhumbix, ClockShark, ~$8–15 US per user per month).** Reasonable at 30+ field
  staff. At RAM's size it is $1,500–3,000/yr for something that still would not know RAM's cost codes or feed ramfin.

## Where it runs

The app is plain static files, so it can be hosted anywhere. Two paths, pick one:

**1. GitHub Pages (free, already wired).** `.github/workflows/timecards-pages.yml` publishes `timecards/app` every
time it changes on the default branch. One-time setup: repository **Settings → Pages → Build and deployment → Source:
GitHub Actions**. The app then lives at `https://ramexcavating.github.io/Ram-web-design/`. GitHub Pages on a *private*
repository needs a GitHub Team plan; on a public repository it is free (the app contains no employee data, only the
cost code and job lists, which are not secret).

**2. Cloudflare Pages or Netlify (free).** Connect the repo, set the publish directory to `timecards/app`, done.
Either gives a custom domain for free.

**Custom domain (recommended before rollout):** point `time.ramexcavating.ca` at whichever host you choose (a CNAME
record in GoDaddy DNS; the host's dashboard shows the exact target). A short, RAM-branded link is what goes on the
onboarding sheet and in the welcome text.

## Onboarding a new employee

1. Text or email them the link. Suggested wording:
   > Welcome to RAM. Your timecard is here: https://time.ramexcavating.ca — open it on your phone, tap Share → Add to
   > Home Screen (iPhone) or ⋮ → Add to Home screen (Android). Put your name in under **Me**. Fill it in at the end of
   > each shift and tap **Email**. Questions: [payroll contact].
2. Add the same link to the **Employee Resources** page under *Payroll and Timesheets* (`docs/page-copy/18-employee-resources.md`).
3. Print the QR code for the link on the orientation package and the lunch-trailer wall. (Any free QR generator; the
   link is public.)

## How a card gets to payroll and job cost

```
phone ──email/share/copy──▶ accounts@ramexcavating.ca ──ramfin ingest──▶ timesheets + time_entries + timecard_days
                                                                   └─▶ filed: 04_PAYROLL/01_TIMESHEETS/<yyyy>/PP_<end>/<end>_<NAME>_Timecard.txt
```

Every card ends with a machine block:

```
--RAMTC1--
{"v":1,"employee":"Ed Smith","periodEnd":"2026-09-12","days":[{"date":"2026-09-03","loa":true,"pu":false,"km":0,
 "lines":[{"job":"260805","cc":"2-200","reg":8,"ot":1,"dt":0,"unit":"EX-03","eq":9,"desc":"Water main Sta 1+00 to 1+60"}]}]}
--END--
```

`ramfin ingest` sees the subject `RAM Timecard | <name> | <date or PP end>` in any monitored mailbox, stores the body,
and `ramfin process` parses the block deterministically (no AI call). Unknown job numbers, cost codes or unit IDs, a
day over 14 hours, or a card from a name not in the employee list become action items in the daily digest instead of
silently landing. A re-sent day replaces the earlier version of that day only; the rest of the pay period is untouched.

You can also paste a card into a file and run `ramfin timecards import card.txt`, and `ramfin timecards reference`
regenerates `timecards/app/data/reference.json` from the finance database so the pickers follow the job list ramfin
already maintains.

## Keeping the lists current

- **Jobs:** edit `timecards/data/jobs.csv` (or, once ramfin is the source of truth, let `ramfin timecards reference`
  write the file). Closed jobs come off the list so nobody codes to them.
- **Cost codes:** export the standard list from SharePoint
  (`01_BUSINESS_FINANCE/03_AP/5.1.08 Budget & Cost Codes/260112_Standard Cost Codes List RAM.xlsx`) to
  `timecards/data/cost_codes.csv` with columns `code,description,category`.
- **Equipment:** `timecards/data/equipment.csv` mirrors `RESOURCES/02_RESOURCES/04_EQUIPMENT/01_EQUIPMENT_INVENTORY/Equipment inventory.xlsx`.
- Run `python3 timecards/tools/build_reference.py`, commit, push. Phones pick the new lists up next time they are online
  (there is also a **Refresh lists** button under **Me**).

## Things to decide before rollout

1. **Deadline and cadence.** The app computes the bi-weekly Saturday pay-period end from the 2026-08-29 anchor. If the
   period ever changes, edit `payPeriod` in `tools/build_reference.py`.
2. **Send-to address.** Defaults to `accounts@ramexcavating.ca`, already monitored by ramfin. Employees can override it
   under **Me** if you ever want a dedicated `timecards@` address.
3. **Daily or per-period sending.** Both work. Daily is better for you: job cost is current to yesterday, and a missed
   day is caught while people remember it. The pay-period send stays for anyone who prefers the old rhythm.
4. **Supervisor sign-off.** The paper sheet has a supervisor signature line. Digital sign-off belongs in ramfin's review
   workbook (the timesheet is `received` until approved), not on the phone. That is a small follow-up once cards are
   flowing.

## What this unlocks (why it is worth doing now)

- **Equipment O&O rates from real hours.** Unit hours by cost code feed the Phase 5 equipment economics in
  `finance/docs/ROADMAP.md`. Today those hours are not captured anywhere.
- **Job cost that is current.** Labour and equipment by cost code the morning after, not at month end from paper.
- **Bids that learn.** Actual hours per cost code per job is the production-rate library estimating has been missing.
- **DFA / force-account billing.** Cards give the daily labour and equipment detail the DFA workbooks (MDM, Knappett,
  Ambrus, CR Waterhouse) are filled from by hand today.
