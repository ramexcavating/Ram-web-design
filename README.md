# RAM Excavating — Website Build Brief

> **Also in this repository:** [`timecards/`](timecards/README.md) — the RAM Timecard phone app for crews (job, cost code, labour and equipment hours), and [`finance/`](finance/README.md) — `ramfin`, the financial operations system (receipts, AP/AR, bank reconciliation, timesheets, job cost, 13-week cash flow). Start with [`finance/docs/ARCHITECTURE.md`](finance/docs/ARCHITECTURE.md).

Everything needed to take **ramexcavating.ca** from a single page to a full 19-page site, inside the website builder it already runs on. No developer, no new hosting, no code.

## Start here

**[`docs/website-build-brief.md`](docs/website-build-brief.md)** — read this first. It covers:

- **Part 1** — six problems on the live site to fix before adding anything (four are free and take under an hour)
- **Part 2** — the 19-page site map and navigation structure
- **Part 3** — canonical address/phone, footer block, and the call-to-action used on every page
- **Part 4** — title tags and meta descriptions for all 19 pages, character-counted
- **Part 5** — target keyword list with geographic modifiers
- **Part 6** — Google Business Profile setup, including a paste-ready business description
- **Part 7** — build order in six stages, so the site is never broken mid-way
- **Part 8** — quarterly maintenance checklist
- **Part 9** — what to measure and how to set it up
- **Part 10** — every blank you need to fill, in one list

## Page copy

One file per page in [`docs/page-copy/`](docs/page-copy/). Open a file, create the page in the builder, paste the copy across.

| File | Page | URL |
|---|---|---|
| `01-home.md` | Home | `/` |
| `02-services-overview.md` | Services | `/services` |
| `03-civil-construction.md` | Civil Construction | `/services/civil-construction` |
| `04-water-sewer-installation.md` | Water & Sewer Installation | `/services/water-sewer-installation` |
| `05-mining-construction.md` | Mining Construction | `/services/mining-construction` |
| `06-industrial-construction.md` | Industrial Construction | `/services/industrial-construction` |
| `07-road-building-highway.md` | Road Building & Highway | `/services/road-building-highway-construction` |
| `08-earthworks-site-preparation.md` | Earthworks & Site Preparation | `/services/earthworks-site-preparation` |
| `09-land-clearing.md` | Land Clearing | `/services/land-clearing` |
| `10-auger-boring-trenchless.md` | Auger Boring & Trenchless | `/services/auger-boring-trenchless` |
| `11-hdpe-pipe-fusion.md` | HDPE Pipe Fusion | `/services/hdpe-pipe-fusion` |
| `12-dewatering-environmental.md` | Dewatering & Environmental | `/services/dewatering-environmental` |
| `13-projects.md` | Projects | `/projects` |
| `14-about.md` | About & Capabilities | `/about` |
| `15-safety.md` | Safety & COR | `/safety` |
| `16-careers.md` | Careers | `/careers` |
| `17-our-team.md` | Our Team | `/our-team` |
| `18-employee-resources.md` | Employee Resources | `/employee-resources` |
| `19-contact.md` | Contact | `/contact` |

## Word version

**`RAM-Website-Build-Brief.docx`** — the whole thing as a single Word document, for reading offline, copying from, or sharing with whoever maintains the site.

## Placeholders

Anything in `[[ DOUBLE BRACKETS ]]` needs a real value from RAM before that page goes live. Every one is listed in **Part 10** of the brief. The ones that block the most work:

1. **Canonical address and phone** — the site says 1280 Quesnel-Hixon Rd / (250) 617-5297; the directories say 1346 Winword Rd / (250) 983-5305. Pick one and standardise it everywhere.
2. **Real projects** — six good ones with photos beat twelve vague ones.
3. **Bonding capacity and insurance limits** — the numbers procurement officers screen on first.
4. **COR certificate number and expiry.**

## If you'd rather not do this in the builder

The brief assumes you're staying on the current builder. If you change your mind, everything here also works as a developer brief — or ask and the same content can be built out as a real static site in this repo, hosted free and pointed at the domain when ready.
