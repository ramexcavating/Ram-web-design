# Getting started (for Rodney, no technical background assumed)

This is the order to do things in. Each step says who does it, how long it takes, and what you will see.
Where it says "I", that means Claude in a Claude Code session with this repository open.

## What you are setting up, in one picture

```
 Your mailboxes, CamScanner, bank CSVs ──► ramfin (runs every weekday morning) ──► SharePoint folders, filed and named
                                              │                                        Weekly review workbook (Excel)
                                              │                                        Weekly Managers Report (Word)
                                              └──────────────────────────────────────► A short email: what needs you
```

The program is plain code that lives in this repository. It needs four keys to do its job: one to read your mail
and write to SharePoint, one to read the old ramcontracting@live.ca mailbox, one for Claude, and one for QuickBooks.
Getting those keys is the only part that needs you personally, because they prove to Microsoft, Anthropic and Intuit
that RAM has authorised it.

## Step 1: the Microsoft key (you, 15 minutes, once)

You are the administrator of RAM's Microsoft 365, so only you can do this.

1. Go to **https://entra.microsoft.com** and sign in as rmickey@ramexcavating.ca.
2. Left menu: **Applications → App registrations → New registration**.
   - Name: `RAM Finance Automation`
   - Supported account types: **Accounts in any organizational directory and personal Microsoft accounts**
     (this is what lets it also read the old live.ca mailbox after you sign in once).
   - Redirect URI: leave blank. Click **Register**.
3. On the app's Overview page copy two values into a note: **Application (client) ID** and **Directory (tenant) ID**.
4. Left menu of the app: **Certificates & secrets → New client secret**. Description `ramfin`, expiry 24 months, Add.
   Copy the **Value** immediately; it is shown once. That is the third value.
5. Left menu: **API permissions → Add a permission → Microsoft Graph**:
   - **Application permissions**: `Mail.Read`, `Mail.Send`, `Sites.ReadWrite.All`. Add.
   - **Delegated permissions**: `Mail.Read`, `User.Read`. Add.
   - Click **Grant admin consent for RAM Excavating** and confirm.
6. Left menu: **Authentication → Advanced settings → Allow public client flows: Yes**. Save.
   (That is what makes the one-time "enter this code" sign-in for the old mailbox work.)

You now have `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`.

## Step 2: the Claude key (you, 3 minutes)

**https://console.anthropic.com** → API Keys → Create key → name it `ramfin`. Copy it. That is `ANTHROPIC_API_KEY`.
Usage at 300 documents a month is under $10.

## Step 3: the QuickBooks key (you and me together, 20 minutes; can wait until week 2)

1. **https://developer.intuit.com** → sign in with the QuickBooks login → Dashboard → **Create an app** →
   QuickBooks Online and Payments → name `RAM Finance` → scope `com.intuit.quickbooks.accounting`.
2. **Keys & credentials → Production** gives `QBO_CLIENT_ID` and `QBO_CLIENT_SECRET`.
3. For the refresh token and realm id, open the **OAuth 2.0 Playground** from the same developer site, choose the
   RAM company file, click through **Get authorization code → Get tokens**. Copy **Refresh token** and **Realm ID**.
   If this step is confusing, stop here and ask me in a session: I will talk you through the screen you are on.

## Step 4: where the keys go (you, 10 minutes)

Pick one. Both work; A is recommended.

**A. GitHub (recommended: runs on its own, nothing to keep switched on).**
GitHub is the website that stores this code. You already have an account because Claude connected to it.
1. Go to **https://github.com/ramexcavating/Ram-web-design/settings/secrets/actions**.
2. Click **New repository secret**. Name `MS_TENANT_ID`, paste the value, **Add secret**.
3. Repeat for `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `ANTHROPIC_API_KEY`, and later the four `QBO_*` values.
4. One more secret called `RAMFIN_CONFIG_B64`. I will hand you this value ready to paste once we finish `config.yaml`.
5. Tell me it is done. I turn the schedule on. From then on it runs weekday mornings at 6:30 and you get an email.
   You never need to visit GitHub again unless a key expires (the Microsoft secret lasts 24 months; I will remind you).

**B. The office PC.** Same keys typed into a file called `.env` next to the program, and a Windows scheduled task.
Works, but the PC has to be on at 6:30 and someone has to keep Python updated on it.

## Step 5: the one-time sign-in for the old mailbox (you, 2 minutes)

In a Claude Code session I run `ramfin auth legacy`. It prints a web address and a nine-character code. You open
the address on your phone or laptop, type the code, sign in as ramcontracting@live.ca, click Accept. Done. Nothing
in that mailbox changes and nothing is forwarded; the program simply reads it the way Outlook on your phone does.
The sign-in is remembered on SharePoint with the database and renews itself.

## Step 6: teach it RAM's names (me, with your answers, 30 minutes)

I export the 825 cost codes and the vendor list from the AP register, load the active jobs with their SharePoint
folders, the debts (Community Futures, CWB, CEBA, Lending Loop, property tax), the recurring consulting income, and
employee base rates. I will ask you about anything I cannot find: mostly "is this supplier critical" and "which
job is this".

## Step 7: the first run and the first review (you and me, one hour)

I run it over the last 90 days of mail. You open `yymmdd_RAM_WEEKLY_REVIEW.xlsx` from `03_CASHFLOW_TRACKING`
and go down the yellow cells: fill in a job, pick a cost code, confirm an amount. Save. I run `ramfin review`
and it learns. The second week there will be far fewer yellow cells; by the fourth, a handful.

When two consecutive weekly reports agree with the Cowork cash flow tool, we retire the Cowork Monday task.

## What the files are

- **.md files** are plain text documents. On GitHub they display formatted when you click them. On your computer
  they open in Notepad, Word or any browser. You do not have to touch them; they are my notes to future-me and to
  anyone who maintains this after me. Anything meant for you to read or file is produced as Word or Excel.
- **.yaml** is the settings file (which mailboxes, which folders, the $60K floor). I edit it; you approve.
- **.py** is the program. You never open it.
- **ramfin.sqlite** is the database. It lives on SharePoint in `03_CASHFLOW_TRACKING/_ramfin`. Do not open or move it.

## What runs where, after this is done

| Job | Today | After |
|---|---|---|
| Monday cash flow tool update | Cowork scheduled task | ramfin, Monday 5:30 |
| Weekly Managers Report | Cowork, Word to SharePoint | ramfin, same file name and folder |
| Equipment Maintenance Log | Cowork, Thursday | ramfin files the repair receipts and costs them per unit; the narrative log can stay in Cowork for now or fold in next |
| Weekly Priorities Summary, Weekly Business Review, Lead Report | Cowork | Stay in Cowork; they read the ramfin outputs instead of re-reading the mailboxes |
