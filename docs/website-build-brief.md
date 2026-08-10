# RAM Excavating Limited — Website Build Brief

**Prepared for:** Rodney Mickey, RAM Excavating Limited
**Date:** 10 August 2026
**Purpose:** Turn ramexcavating.ca from a single page into a full multi-page site inside your existing website builder.

---

## How to use this brief

You are staying on your current website builder (GoDaddy / Wix family — your images serve from `wsimg.com`). Nothing here requires a developer or new hosting.

Each page has its own file in `docs/page-copy/`. Open one file, create the matching page in the builder, and paste the copy across. Everything is written to be pasted as-is.

Every file follows the same layout:

| Field | What to do with it |
|---|---|
| **URL slug** | Set the page's URL/permalink to this |
| **Nav label** | The wording that appears in your menu |
| **Title tag** | Builder field is usually "SEO title" or "Page title" — under 60 characters |
| **Meta description** | Builder field is usually "SEO description" — under 155 characters |
| **H1** | The page's single main heading. One per page, never two |
| **Body copy** | Paste directly. `##` = a section heading, `###` = a sub-heading |
| **Images** | What photo to use and the alt text to type into the image's alt/description field |
| **Internal links** | Links to add from this page to others |
| **Target keywords** | What this page is trying to rank for. Already worked into the copy — do not add more |

Anything wrapped in `[[ DOUBLE BRACKETS ]]` is a placeholder **you must fill in or delete before publishing.** Every one of them is listed in "Placeholders you must fill" at the end of this brief.

---

## Part 1 — Fix these before you add a single new page

I reviewed your live homepage. These are working against you right now, and four of them are free to fix in under an hour.

### 1.1 Dead navigation links (fix first)

Your menu already has **Projects** and **NEWS / BLOG** items, but they point at pages that don't exist:

- `Projects` → `/projects` — no page there
- `NEWS / BLOG` → `/news-%2F-blog` — no page there, and the URL contains an encoded slash (`%2F`), which is a malformed slug

A procurement officer or GC estimator who clicks Projects and gets nothing concludes the company is small or inattentive. That is the exact opposite of what the page is for.

**Do this:** either build those pages now (Projects copy is in this brief) or remove the menu items until they exist. Do not leave them dangling.

**On the blog:** you do not need one. Your buyers are mines, municipalities, engineering consultants and GC estimators — they do not read contractor blogs, and a blog that goes quiet after three posts reads worse than no blog. Rename that menu item **Projects** or delete it. If you want a place for occasional news, put it as a short "Recent Work" section on the Projects page instead.

### 1.2 Your mission statement is pasted into five different sections

This paragraph currently appears verbatim under **Our Mission**, **Civil Construction**, **Project Management System**, and again elsewhere:

> "At RAM Excavating, we strive to work with our clients in the civil construction industry to create quality projects on budget and on time…"

The Quality Control System and Safety Program sections have the same problem — they repeat the Mining Construction and Industrial Construction text instead of describing quality control and safety.

Two costs. Google reads a page that says the same thing five times as thin content and ranks it lower. And a buyer reading it notices immediately that nothing is actually being said about your quality control system.

**Do this:** replace all of it with the unique copy in `docs/page-copy/01-home.md`, and give Quality Control and Safety their own real descriptions (also written for you).

### 1.3 Broken images

Several image slots on the homepage are serving placeholder GIFs rather than photos. For a civil contractor, project photos *are* the credibility — a buyer's 60-second check is mostly visual.

**Do this:** re-upload every broken image. If you don't have a photo for a slot, delete the slot rather than showing a broken one. Prioritise: crews working in PPE, equipment on site, completed water/sewer and road work.

### 1.4 Text truncated mid-sentence

Your Quality Control section ends with "…preferred choice f" — cut off. It's inside a "Show More / Show Less" expander that isn't holding the full text.

**Do this:** the replacement copy is short enough that you can drop the expanders entirely. Show the whole thing.

### 1.5 The Alberta location line is one run-together string

Your footer currently reads:

> AB Location: 9701 99 Ave Grande Cache AB | (250) 617-5297 | Info@ramexcavating.ca

Address, phone and email are jammed into the AB line, which makes it look like the phone number belongs to Grande Cache only. Correct formatting is in Part 3.

### 1.6 Your address and phone don't match your directory listings — fix this one properly

This is the most damaging item on the list, and the only one I can't fix for you.

| Source | Address | Phone |
|---|---|---|
| ramexcavating.ca | 1280 Quesnel-Hixon Road, Quesnel BC | (250) 617-5297 |
| Yellow Pages, Canpages, iBegin, Yelp | 1346 Winword Rd, Quesnel BC | (250) 983-5305 |

Google cross-references your name, address and phone ("NAP") across the web to decide how much to trust your location. Two different addresses and two different phone numbers for one company suppresses your local ranking and splits your reviews and citations across two identities. It also means a buyer who Googles you may phone a number you're not answering.

**Do this, in order:**

1. **Decide which address and phone are canonical.** Pick the one you actually want work enquiries going to.
2. Write it down in exactly one format and never vary it — not even "Rd" vs "Road" or "(250) 617-5297" vs "250-617-5297". Use the format in Part 3.
3. Update, in this order: Google Business Profile → website footer → Yellow Pages → Canpages → Yelp → iBegin → BC Local → any association or prequalification directory (BidCentral, ISNetworld, ComplyWorks, Avetta).
4. If both addresses are real premises, make the canonical one your primary and either delete the second listing or set it up properly as a second location — never as a duplicate of the first.

**I have used the website's current values (1280 Quesnel-Hixon Road, (250) 617-5297) throughout this brief.** If the Winword Rd address is the correct one, find-and-replace before you publish.

---

## Part 2 — Site structure

19 pages. You do not have to build them all at once — see the build order in Part 7.

```
Home                                   /
About                                  /about
  └ Our Team                           /our-team
  └ Safety & COR                       /safety
Services                               /services
  ├ Civil Construction                 /services/civil-construction
  ├ Water & Sewer Installation         /services/water-sewer-installation
  ├ Mining Construction                /services/mining-construction
  ├ Industrial Construction            /services/industrial-construction
  ├ Road Building & Highway            /services/road-building-highway-construction
  ├ Earthworks & Site Preparation      /services/earthworks-site-preparation
  ├ Land Clearing                      /services/land-clearing
  ├ Auger Boring & Trenchless          /services/auger-boring-trenchless
  ├ HDPE Pipe Fusion                   /services/hdpe-pipe-fusion
  └ Dewatering & Environmental         /services/dewatering-environmental
Projects                               /projects
Careers                                /careers
  └ Employee Resources                 /employee-resources
Contact                                /contact
```

### Top navigation

Keep it to six items. More than that and it wraps badly on a phone, which is where site foremen and estimators will open it.

```
Home    About ▾    Services ▾    Projects    Careers ▾    Contact
```

- **About ▾** drop-down: Our Team, Safety & COR
- **Services ▾** drop-down: all ten service pages
- **Careers ▾** drop-down: Employee Resources
- Add a phone number as a button at the top right: **(250) 617-5297** — on mobile make it a tappable `tel:` link. Buyers on site call; they don't fill in forms.

### Footer navigation

Repeat the full page list in the footer as plain links. It costs nothing, helps Google find every page, and gives buyers a second path to Projects and Contact.

---

## Part 3 — Global elements (identical on every page)

### Canonical NAP — use this exact wording everywhere

```
RAM Excavating Limited
1280 Quesnel-Hixon Road, Quesnel, BC V2J 7G3, Canada
Phone: (250) 617-5297
Email: Info@ramexcavating.ca
```

Second location, formatted separately:

```
Alberta Office
9701 99 Avenue, Grande Cache, AB, Canada
Phone: (250) 617-5297
Email: Info@ramexcavating.ca
```

`[[ CONFIRM: postal code V2J 7G3 is from your directory listings — verify it matches the Quesnel-Hixon Road address, or remove it ]]`

### Footer block

```
RAM EXCAVATING LIMITED
Civil construction contractor serving British Columbia and Alberta since 1986.
COR® certified through the BC Construction Safety Alliance.

BC OFFICE
1280 Quesnel-Hixon Road
Quesnel, BC, Canada
(250) 617-5297
Info@ramexcavating.ca

ALBERTA OFFICE
9701 99 Avenue
Grande Cache, AB, Canada
(250) 617-5297
Info@ramexcavating.ca

HOURS
Monday to Friday, 9:00 a.m. – 5:00 p.m.
Saturday and Sunday by appointment

[full page link list]

Facebook  |  LinkedIn  |  YouTube

© 2026 RAM Excavating Limited. All rights reserved.
```

Two fixes in there: the copyright year currently reads 2025 — update it, and set a reminder to do so each January. And `[[ SUPPLY: your LinkedIn and YouTube URLs — the icons are on the site now but I could only confirm facebook.com/Ramexcavating ]]`

### Standard call-to-action block

Put this at the bottom of every page except Contact and Employee Resources. Same wording every time.

```
## Discuss your project with RAM

Tell us what you're building and we'll tell you straight away whether
we're the right contractor for it. Estimating enquiries, prequalification
packages and tender invitations all go to the same place.

Call (250) 617-5297   ·   Email Info@ramexcavating.ca

[ Request a quote ]  → /contact
```

### Trust bar

A single horizontal strip directly under the header on Home, About, Safety and every service page. Four items, no images needed:

```
Since 1986   ·   COR® Certified (BCCSA)   ·   BC · AB · SK   ·   Municipal · Mining · Industrial · MOTI
```

This is doing real work. It answers "are they established, are they safe, do they work where I am, have they done my kind of job" in one line, above the fold, before anyone scrolls.

---

## Part 4 — Title tags and meta descriptions

Paste these into your builder's SEO fields. Every one is unique — duplicate tags across pages actively hurt you. Character counts are shown so you can see there's no truncation risk.

| Page | Title tag (≤60) | Meta description (≤155) |
|---|---|---|
| Home | Civil Construction Contractor in BC & Alberta \| RAM (57) | COR-certified civil construction contractor serving BC and Alberta since 1986. Water and sewer, roads, mine sites and industrial earthworks. (139) |
| About | About RAM Excavating \| Civil Contractor Since 1986 (51) | Family-founded in Quesnel BC in 1986. Our capabilities, equipment fleet, service area and certifications as a heavy civil contractor. (134) |
| Our Team | Our Team \| RAM Excavating Limited (34) | Meet the people who run RAM Excavating — leadership, estimating, project management and safety contacts for your project. (122) |
| Safety & COR | Safety & COR Certification \| RAM Excavating (43) | RAM Excavating is COR certified through the BC Construction Safety Alliance. Our safety program, record and prequalification documents. (135) |
| Services | Civil Construction Services in BC & Alberta \| RAM (49) | Site servicing, water and sewer, road building, mine site construction, land clearing, auger boring and HDPE fusion across BC and Alberta. (138) |
| Civil Construction | Civil Construction Contractor Quesnel & Cariboo BC (50) | Municipal civil construction across western Canada — watermains, sanitary and storm sewer, street reconstruction and underground utilities. (139) |
| Water & Sewer | Water & Sewer Installation Contractor BC (40) | Watermain, sanitary and storm sewer installation and replacement for municipalities and developers across BC and Alberta. Since 1986. (132) |
| Mining Construction | Mine Site Construction Contractor BC (37) | Haul roads, portal construction, settling ponds and dump site management for new mine developments and operating mines in BC and Alberta. (137) |
| Industrial Construction | Industrial Construction Contractor BC & Alberta (48) | Plant site civil works, sawmill builds, infrastructure renewal and site maintenance across BC, Alberta and Saskatchewan. (120) |
| Road Building | Road Building & Highway Construction BC \| MOTI (46) | BC MOTI highway construction and road building to provincial standards. Grade, subgrade, drainage and resource road construction. (129) |
| Earthworks | Earthworks & Site Preparation Contractor BC (43) | Bulk excavation, mass grading, structural fill and pad construction for industrial, commercial and residential development sites. (129) |
| Land Clearing | Land Clearing Contractor Quesnel & Cariboo BC (45) | Right-of-way and site clearing, grubbing, mulching and debris management for mine, pipeline, road and development projects in BC. (128) |
| Auger Boring | Auger Boring & Trenchless Contractor BC (39) | Trenchless crossings under highways, rail and watercourses by auger boring — no open cut, no traffic closure, no watercourse disturbance. (138) |
| HDPE Fusion | HDPE Pipe Fusion Contractor BC & Alberta (40) | Certified butt and electrofusion of HDPE pipe for water, sewer, mine dewatering and industrial process lines. Field crews across BC and AB. (140) |
| Dewatering | Dewatering & Environmental Contractor BC (40) | Construction dewatering, sediment and erosion control, water treatment and environmental compliance for civil and mine site works in BC. (135) |
| Projects | Projects \| RAM Excavating Limited (34) | Completed civil construction, mine site, industrial and highway projects across BC and Alberta. Scope, client type and location for each. (137) |
| Careers | Careers \| RAM Excavating Limited (32) | Operators, pipelayers, foremen and labourers wanted in Quesnel BC and Grande Cache AB. Competitive wages, steady work, safety-first crews. (139) |
| Employee Resources | Employee Resources \| RAM Excavating (36) | Forms, policies, safety documents, timesheets and contacts for RAM Excavating employees. (88) |
| Contact | Contact RAM Excavating \| Quesnel BC & Grande Cache AB (54) | Call (250) 617-5297 or email Info@ramexcavating.ca. Offices in Quesnel BC and Grande Cache AB. Tender invitations and estimating enquiries welcome. (152) |

---

## Part 5 — Target keyword list

Your buyers run a small number of very specific searches. This list is deliberately short. You do not need national or high-volume terms — you need to own "[service] + [place]" in your region.

### Primary — highest value, each owned by one page

| Keyword | Owned by |
|---|---|
| civil construction contractor BC | Home |
| civil contractor Quesnel | Civil Construction |
| excavation contractor Quesnel BC | Earthworks & Site Preparation |
| water and sewer installation contractor BC | Water & Sewer |
| mine site construction contractor BC | Mining Construction |
| industrial construction contractor BC | Industrial Construction |
| highway construction contractor BC | Road Building |
| land clearing contractor Quesnel | Land Clearing |
| auger boring contractor BC | Auger Boring & Trenchless |
| HDPE pipe fusion BC | HDPE Fusion |

### Secondary — work these in naturally where they fit

- site servicing contractor Cariboo
- underground utilities contractor Prince George
- watermain replacement contractor BC
- storm sewer contractor BC
- civil contractor Williams Lake
- civil contractor Prince George
- haul road construction BC
- resource road construction BC
- earthworks contractor Cariboo
- general contractor Quesnel BC
- construction dewatering BC
- civil construction Grande Cache AB
- civil contractor Grande Prairie

### Geographic modifiers to use

Quesnel, Cariboo, Cariboo Regional District, Williams Lake, Prince George, Prince Rupert corridor, northern BC, British Columbia, Grande Cache, Grande Prairie, Alberta, Saskatchewan.

### One rule

Write for the buyer first, then check the term is present. Never repeat a keyword to hit a count — Google has been penalising that for over a decade, and a procurement officer reading stuffed copy will just leave.

---

## Part 6 — Google Business Profile

Your website and your Google Business Profile work as a pair. For a regional contractor the profile often produces more real enquiries than the website does, and it is free. Do this the same week you launch the new pages.

**Business name:** `RAM Excavating Limited` — exactly that. Do not append "Civil Construction Quesnel" or similar; it breaches Google's naming policy and risks suspension.

**Primary category:** Excavating contractor

**Additional categories:** General contractor, Construction company, Civil engineering company, Road construction company, Demolition contractor, Land clearing service

**Service areas** (up to about 20): Quesnel, Williams Lake, Prince George, Cariboo Regional District, 100 Mile House, Vanderhoof, Bella Coola corridor, Mackenzie, Fort St. James, Grande Cache AB, Grande Prairie AB, Hinton AB

**Services** — add each as its own item, matched to your service pages: Civil construction, Water and sewer installation, Mine site construction, Industrial construction, Road building, Highway construction, Earthworks and site preparation, Land clearing, Auger boring, HDPE pipe fusion, Dewatering, Environmental solutions

**Business description** (750 char limit — this is 715, paste as-is):

> RAM Excavating Limited is a COR-certified civil construction contractor based in Quesnel, British Columbia, working across BC, Alberta and Saskatchewan. Founded in 1986, we have spent nearly four decades building and replacing the infrastructure western Canada runs on — watermains, sanitary and storm sewer, street reconstruction, highway grade, mine site haul roads and portals, and industrial plant site works.
>
> We work for municipalities, regional districts, mines, oil and gas operators, industrial plant owners, developers, general contractors and engineering consultants. Our safety program follows BCCSA's COR standard and provincial and federal regulation on every project.
>
> Estimating and tender enquiries: (250) 617-5297 or Info@ramexcavating.ca

**Hours:** Monday–Friday 9:00 a.m.–5:00 p.m. Set special hours for statutory holidays.

**Photos — the single highest-impact item on this list.** Upload 20+ real photos: completed water and sewer installs, open trench with shoring, haul roads, the equipment fleet, crews in full PPE, finished road surfaces. No stock photography. Add a few new ones every quarter. This is the most persuasive thing about you that a buyer will see, and right now it costs you nothing but the upload.

**Posts:** one or two a month. Completed project, safety milestone, new equipment, hiring. Keeps the profile active, which is a ranking signal.

**Reviews:** your client count is small and your review count will be too — that's normal and fine for B2B. After a job wraps, ask the municipal contact, GC estimator or development manager for a short Google review, and send them the direct review link so it takes 30 seconds. Reply to every review, briefly and professionally. Procurement people read how you respond to a complaint as a signal of how you'd handle a problem on their site.

**Review request message — copy and send:**

> Hi [Name], now that [project] is wrapped up, would you mind leaving RAM a short Google review? A line or two about how the work went is plenty, and it genuinely helps us when new clients are checking us out. Direct link: [review link]. Thanks — appreciate you.

---

## Part 7 — Build order

Do not try to launch 19 pages at once. In this order, each stage stands on its own and the site is never broken mid-way.

**Stage 1 — this week (fixes only, no new pages)**
1. Remove or repoint the dead Projects and NEWS/BLOG menu items (Part 1.1)
2. Replace the duplicated homepage copy with `01-home.md` (Part 1.2)
3. Re-upload broken images, delete slots you can't fill (Part 1.3)
4. Fix the AB footer line and the 2025 copyright year (Part 1.5)
5. Decide your canonical address and phone (Part 1.6) — this decision blocks Stage 4

**Stage 2 — the credibility trio.** These three do more than the other sixteen combined. A buyer who lands on your site needs to see what you've built, who you are, and how to reach you.
6. Projects — `13-projects.md`
7. About — `14-about.md`
8. Contact — `19-contact.md`

**Stage 3 — safety and services hub.** Safety is a prequalification gate for mines and public buyers; they screen on it before they look at price.
9. Safety & COR — `15-safety.md`
10. Services overview — `02-services-overview.md`

**Stage 4 — the five service pages that carry your best keywords**
11. Civil Construction — `03-civil-construction.md`
12. Water & Sewer Installation — `04-water-sewer-installation.md`
13. Mining Construction — `05-mining-construction.md`
14. Industrial Construction — `06-industrial-construction.md`
15. Road Building & Highway — `07-road-building-highway.md`
16. Then update Google Business Profile and all directory listings to your canonical NAP (Part 6 and Part 1.6)
17. Submit your sitemap to Google Search Console (Part 9)

**Stage 5 — remaining service pages, one a week**
18. Earthworks & Site Preparation — `08-earthworks-site-preparation.md`
19. Land Clearing — `09-land-clearing.md`
20. Auger Boring & Trenchless — `10-auger-boring-trenchless.md`
21. HDPE Pipe Fusion — `11-hdpe-pipe-fusion.md`
22. Dewatering & Environmental — `12-dewatering-environmental.md`

**Stage 6 — people pages**
23. Careers — `16-careers.md`
24. Our Team — `17-our-team.md`
25. Employee Resources — `18-employee-resources.md`

---

## Part 8 — Quarterly maintenance checklist

A stale site quietly costs you credibility. Twenty minutes a quarter keeps it earning. Put this in your calendar for the first week of January, April, July and October.

- [ ] **Add one or two recently completed projects to the Projects page, with photos.** This is the highest-value item on the list — fresh proof of work is what makes buyers trust you. If you only do one thing, do this one.
- [ ] Upload 5–10 new photos to Google Business Profile
- [ ] Post once or twice to Google Business Profile
- [ ] Confirm services, service areas and both office addresses are still accurate
- [ ] Confirm the equipment list on About still matches the fleet
- [ ] Check COR certification, insurance limits and bonding capacity are current — update immediately after any renewal
- [ ] **Test the contact form yourself** — submit it and confirm the email arrives. Silently broken forms are the single most common way a website loses work
- [ ] Test the Careers application form the same way
- [ ] Click every menu item and check nothing 404s
- [ ] Open the site on a phone and check it reads properly
- [ ] Check the copyright year in the footer (January only)
- [ ] Ask one satisfied client from the quarter for a Google review

---

## Part 9 — Measurement

Track what reflects buyer intent, not vanity numbers. Raw traffic is close to meaningless for you — thirty visits from the right five organisations beats three thousand from the general public.

**Set up once:**

1. **Google Search Console** — verify the domain, then submit your sitemap. Your builder generates one automatically, usually at `ramexcavating.ca/sitemap.xml`. Confirm every new page appears in it as you build.
2. **Google Business Profile insights** — already on, nothing to set up.
3. **Make sure form submissions are traceable.** Set the contact form to email a real monitored inbox, and put the page name in the subject line so you know whether an enquiry came from Contact, Careers or a service page.

**Review quarterly, in this order of importance:**

| What | Where | Why it matters |
|---|---|---|
| Qualified enquiries and calls that became real bid opportunities | Your inbox and phone | The only metric that actually matters |
| GBP calls, direction requests, website clicks | GBP insights | Usually more telling than site traffic for a regional contractor |
| Impressions and clicks for "[service] + [region]" queries | Search Console | Tells you whether the service pages are landing |
| Which pages rank, and for what | Search Console | Tells you which service page to strengthen next |

Ignore bounce rate and session duration. They tell you nothing useful about a buyer who found what they needed in forty seconds and picked up the phone.

---

## Part 10 — Placeholders you must fill

Every `[[ DOUBLE BRACKET ]]` item across this brief and the page copy files. Nothing should go live with these still in it.

**Blocks Stage 1**
- Canonical address and phone number — 1280 Quesnel-Hixon Rd / (250) 617-5297 or 1346 Winword Rd / (250) 983-5305 (Part 1.6)
- Quesnel postal code — verify V2J 7G3 or remove it (Part 3)
- LinkedIn and YouTube URLs (Part 3)

**Blocks the Projects page** — `13-projects.md` has twelve placeholder project entries. For each one you keep, supply: project name, client and client type, location, year, scope of work, approximate contract value or a value band, and two or three photos. Six real projects beat twelve vague ones. Delete the rest.

**Blocks the About page** — `14-about.md`
- Equipment fleet list — types and rough counts, e.g. "6 excavators 20–50 tonne, 4 rock trucks, 3 dozers"
- Bonding capacity — single project limit and aggregate limit
- Insurance limits — commercial general liability, auto, equipment
- Employee headcount, or a range
- Current certifications and memberships beyond COR

**Blocks the Safety page** — `15-safety.md`
- COR certificate number and expiry date
- Current or three-year average injury frequency rate, if you're willing to publish it
- Which prequalification networks you're registered in: ISNetworld, ComplyWorks, Avetta, BidCentral, BC Bid
- Name and title of your safety contact

**Blocks Our Team** — `17-our-team.md`
- For each person: name, title, years with RAM, years in industry, a two-line background, photo. Rodney Mickey plus 4–8 others is right.

**Blocks Careers** — `16-careers.md`
- Current open positions
- Wage ranges or bands, if you'll publish them
- Benefits: extended health, RRSP matching, camp and LOA arrangements, training paid
- Where applications should go — email address or a form

**Blocks Employee Resources** — `18-employee-resources.md`
- Which forms to link and where they live
- Payroll cut-off day and pay dates
- Emergency and dispatch numbers
- Whether this page should be password protected

---

## One thing that will outperform everything in this brief

Worth saying plainly, because it sits outside the website and it's where your work actually comes from.

Mines, oil and gas operators, and public bodies do not find contractors by Googling. They award to whoever is already on their prequalified vendor list. Registration on **BC Bid**, **BidCentral** and the safety prequalification networks (**ISNetworld**, **ComplyWorks**, **Avetta**) is the literal front door for that work, and it is mostly free or low cost. Being COR certified already puts you through the hardest gate — the registrations just make you visible to buyers who are looking.

And the highest-leverage audience of all is engineering consultants and GC estimators in your region. Get onto their bid lists and you get a recurring stream of invited opportunities without bidding a single open tender.

The website's job is to make you look like a serious heavy-civil contractor when those people look you up — and it will, once this is built. But it is the backstop, not the engine. Happy to build out the procurement-registration and bid-list plan next if it's useful.
