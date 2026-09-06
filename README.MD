# Megadox — NSE & Nifty Indices Market Data Pipeline

A collection of Python scripts that scrape, clean, and ingest Indian equity market data — index OHLC prices, valuation ratios (PE/PB/Div Yield), market breadth (advance/decline), and India VIX — from **NSE India** and **NiftyIndices** into a **CockroachDB** (Postgres-compatible) database. The project also documents how the undocumented NSE/NiftyIndices endpoints were reverse-engineered.

> ⚠️ **Disclaimer**: This project interacts with public-facing but undocumented/unofficial NSE India and NiftyIndices web endpoints (the same ones their own website frontends call). It is intended for personal research, learning, and analytics purposes only. It is not affiliated with, endorsed by, or supported by NSE or NiftyIndices. Endpoints, payload formats, and rate limits can change or break at any time without notice. Review and respect the [NSE Terms of Use](https://www.nseindia.com) and [NiftyIndices Terms of Use](https://www.niftyindices.com) before using this in any production or commercial context.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Data Sources](#data-sources)
- [Project Structure](#project-structure)
- [Database Schema (expected tables)](#database-schema-expected-tables)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
- [CI/CD (GitHub Actions)](#cicd-github-actions)
- [How the Scraping Works](#how-the-scraping-works)
- [Reverse-Engineering Notes](#reverse-engineering-notes)
- [Logging & Email Reports](#logging--email-reports)
- [Known Quirks & Gotchas](#known-quirks--gotchas)
- [Roadmap Ideas](#roadmap-ideas)
- [License](#license)

---

## Overview

This pipeline pulls four categories of market data for NSE indices (NIFTY 50, sectoral indices, strategy indices, thematic indices, fixed-income indices, etc.):

| Data Type | Description | Target Table |
|---|---|---|
| **Price (OHLC)** | Daily open/high/low/close, shares traded, turnover | `price_metadata` |
| **Valuation** | PE ratio, PB ratio, dividend yield | `valuation_metadata` |
| **Market Breadth** | Market-wide advances/declines and ratio | `advance_decline_metadata` |
| **India VIX** | Volatility index OHLC, previous close, points/percentage change | `india_vix_metadata` |

Each data type has a **daily fetcher** (pulls the previous calendar day's data — `date.today() - timedelta(days=1)` — meant to run on a schedule) and a **historical ingestion** script (interactively backfills a custom date range in rolling 30-day windows, with automatic fallback between two data sources for price and valuation).

---

## Architecture

```
                         ┌─────────────────────────┐
                         │   index_metadata table   │  (index_id, index_long_name,
                         │      (CockroachDB)       │   trading_index_name, source...)
                         └────────────┬────────────┘
                                      │ lookup name for index_id
                                      ▼
        ┌──────────────────────────────────────────────────────┐
        │                    Fetcher Scripts                    │
        │  ┌────────────┐  ┌────────────┐  ┌──────────────────┐ │
        │  │ NSE India  │  │  Nifty     │  │  Random UA +      │ │
        │  │ REST API   │  │  Indices   │  │  curl_cffi        │ │
        │  │ (GET)      │  │  (POST)    │  │  browser          │ │
        │  │            │  │            │  │  impersonation    │ │
        │  └─────┬──────┘  └─────┬──────┘  └──────────────────┘ │
        └────────┼───────────────┼───────────────────────────────┘
                 │               │
                 ▼               ▼
        ┌───────────────────────────────────┐
        │     Clean → Decimal-cast → Null    │
        │        normalize → De-dupe         │
        └────────────────┬────────────────────┘
                          ▼
        ┌───────────────────────────────────┐
        │   price_metadata / valuation_/     │
        │   advance_decline_/ india_vix_     │
        │           (CockroachDB)            │
        └────────────────┬────────────────────┘
                          ▼
                 ┌──────────────────┐
                 │  logs_email.py    │  → emails the day's
                 │  (SMTP over SSL)  │    execution log as an
                 └──────────────────┘    attachment
```

**Key design choices:**
- **Two interchangeable data sources** (NSE India + NiftyIndices) for price/valuation history — if one source is missing data for a stale index, the other can be used as a fallback for that same date range.
- **Insert-or-update merge logic** — *implemented only in `data_ingestion_price.py` and `valuation_data_ingestion.py`*: before writing a row, the script `SELECT`s the existing row, counts how many non-null fields it has vs. the incoming API record, and only overwrites if the incoming record is *at least as complete*. This avoids a "richer" existing row being clobbered by a sparser one. `vix_historical_data_fetch.py` and `adv_dec_ingestion.py` do a plain `INSERT` with no such check — see [Known Quirks](#known-quirks--gotchas).
- **Trading-calendar reconciliation**: `pandas_market_calendars` (NSE `XNSE`, BSE `XBOM`) is used to compute the expected set of trading days for a date range, then diffed against what was actually ingested, to flag gaps. This runs in the two price/valuation historical-ingestion scripts.
- **Randomized User-Agent + `curl_cffi` impersonation** on every session to reduce the chance of being blocked/rate-limited by NSE's anti-bot layer, plus a random 1–10s sleep between requests.

---

## Data Sources

### 1. NSE India (`nseindia.com`)
Official exchange REST API (not publicly documented, but used by the NSE website itself).

| Purpose | Endpoint |
|---|---|
| Historical index OHLC | `GET /api/historicalOR/indicesHistory?indexType=<name>&from=<dd-mm-yyyy>&to=<dd-mm-yyyy>` |
| Historical index valuation (PE/PB/Div Yield) | `GET /api/historicalOR/indicesYield?indexType=<name>&from=<dd-mm-yyyy>&to=<dd-mm-yyyy>` |
| India VIX history | `GET /api/historicalOR/vixhistory?from=<dd-mm-yyyy>&to=<dd-mm-yyyy>` |
| Market-wide advance/decline (live) | `GET /api/live-analysis-advance` |
| Market-wide advance/decline (monthly historical) | `GET /api/historicalOR/advances-decline-monthly?year=<MON-YYYY>` |

A session must first `GET https://www.nseindia.com/` to acquire cookies before any API call will succeed — NSE rejects "cold" requests with no prior cookie handshake.

### 2. NiftyIndices (`niftyindices.com`)
The IISL/NSE Indices' own reporting backend, called via `Backpage.aspx` ASMX-style JSON endpoints.

| Purpose | Endpoint |
|---|---|
| Historical OHLC | `POST /Backpage.aspx/getHistoricaldatatabletoString` |
| Historical PE/PB/Div Yield | `POST /Backpage.aspx/getpepbHistoricaldataDBtoString` |
| Index dropdown list (name mapping) | `POST /Backpage.aspx/gethistoricaltypeindexdata` |

Payload shape (double-JSON-encoded, matching exactly what the site's own frontend sends):

```json
{
  "cinfo": "{'name':'NIFTY 50','startDate':'25-Mar-2026','endDate':'25-Mar-2026','indexName':'NIFTY 50'}"
}
```

See [`Reverse_Engineering_API.pdf`](./Reverse_Engineering_API.pdf) and [`Payload_Analysis.pdf`](./Payload_Analysis.pdf) for the full network-tab walkthrough of how these payloads and headers were discovered, including the exact `name` vs. `indexName` field mismatches between the two sites' index catalogs.

---

## Project Structure

```
.
├── .github/
│   └── workflows/
│       ├── price_valuation_india_vix.yml   # Daily: price + valuation + India VIX fetchers (cron, 18:00 IST)
│       └── advance_decline.yml             # Daily: advance/decline fetcher (cron, 18:00 IST)
├── Sample_Emails/                  # Example daily log-report emails from the GCP-VM-cron era
├── .gitignore                      # Excludes .env, venv/, __pycache__/, logs/, etc.
│
├── daily_fetcher_price.py          # Daily OHLC price fetch (NSE India) for all indices
├── data_ingestion_price.py         # Interactive historical OHLC backfill (NSE India OR NiftyIndices)
│
├── valuation_daily_fetcher.py      # Daily PE/PB/Div Yield fetch (NSE India) for all indices
├── valuation_data_ingestion.py     # Interactive historical valuation backfill (NSE India OR NiftyIndices)
│
├── adv_dec_daily_fetcher.py        # Daily market-wide advance/decline fetch (NSE India)
├── adv_dec_ingestion.py            # Interactive historical advance/decline backfill, month-by-month
│
├── india_vix_daily.py              # Daily India VIX OHLC fetch (NSE India)
├── vix_historical_data_fetch.py    # Interactive historical India VIX backfill, rolling 30-day windows
│
├── logs_email.py                   # Emails the day's markdown execution log as an attachment
├── requirements.txt                # Python dependencies
│
├── Reverse_Engineering_API.pdf     # Write-up: reverse-engineering the NiftyIndices private API
├── Payload_Analysis.pdf            # Write-up: NSE India vs NiftyIndices payload/header analysis
└── README.MD
```

### Script categories at a glance

| Script | Cadence | Data Source(s) | Table |
|---|---|---|---|
| `daily_fetcher_price.py` | Daily (cron) | NSE India | `price_metadata` |
| `data_ingestion_price.py` | On-demand / backfill | NSE India **or** NiftyIndices (user choice) | `price_metadata` |
| `valuation_daily_fetcher.py` | Daily (cron) | NSE India | `valuation_metadata` |
| `valuation_data_ingestion.py` | On-demand / backfill | NSE India **or** NiftyIndices (user choice) | `valuation_metadata` |
| `adv_dec_daily_fetcher.py` | Daily (cron) | NSE India | `advance_decline_metadata` |
| `adv_dec_ingestion.py` | On-demand / backfill | NSE India | `advance_decline_metadata` |
| `india_vix_daily.py` | Daily (cron) | NSE India | `india_vix_metadata` |
| `vix_historical_data_fetch.py` | On-demand / backfill | NSE India | `india_vix_metadata` |
| `logs_email.py` | Daily (cron, after fetchers) | — | (emails a log file) |

---

## Database Schema (expected tables)

The scripts assume these tables already exist in CockroachDB (they do **not** create tables).

### Current table snapshot

Output of `SHOW TABLES;` against the live cluster:

| # | Schema | Table | Type | Owner | Est. Row Count | Locality |
|---|---|---|---|---|---|---|
| 1 | public | `advance_decline_metadata` | table | postgres | 23 | REGIONAL BY TABLE IN PRIMARY REGION |
| 2 | public | `index_metadata` | table | postgres | 137 | REGIONAL BY TABLE IN PRIMARY REGION |
| 3 | public | `india_vix_metadata` | table | postgres | 29 | REGIONAL BY TABLE IN PRIMARY REGION |
| 4 | public | `price_data_source_metadata` | table | postgres | 0 | REGIONAL BY TABLE IN PRIMARY REGION |
| 5 | public | `price_metadata` | table | postgres | 4,932 | REGIONAL BY TABLE IN PRIMARY REGION |
| 6 | public | `valuation_data_source_metadata` | table | postgres | 0 | REGIONAL BY TABLE IN PRIMARY REGION |
| 7 | public | `valuation_metadata` | table | postgres | 4,476 | REGIONAL BY TABLE IN PRIMARY REGION |

> **Note:** `price_data_source_metadata` and `valuation_data_source_metadata` exist in the live schema but currently hold **0 rows** and are **not referenced by any script** in this repo. They appear to be reserved for tracking *which* upstream source (NSE India vs. NiftyIndices) supplied each price/valuation row — useful given the dual-source fallback design described in [Architecture](#architecture) — but nothing in the codebase writes to them yet. Populating them (or dropping them if they're stale scaffolding) is a good candidate for the [Roadmap](#roadmap-ideas).
>
> All seven tables use CockroachDB's `REGIONAL BY TABLE IN PRIMARY REGION` locality, i.e. single-region placement pinned to the cluster's primary region rather than multi-region survivability — consistent with this being a personal-scale analytics project rather than a globally-distributed service.

Below is the schema inferred from the `INSERT`/`UPDATE` queries in the code for the five tables the scripts actively use — adjust as needed for your own setup:

```sql
CREATE TABLE index_metadata (
    index_id            INT PRIMARY KEY,
    index_long_name     TEXT NOT NULL,      -- canonical name used by NSE India API
    trading_index_name  TEXT NOT NULL,      -- name used by NiftyIndices API
    source              TEXT,               -- last source used to update this index
    last_updated_time   TIMESTAMP,
    data_origin_date    DATE                -- earliest date successfully backfilled
);

CREATE TABLE price_metadata (
    index_id            INT REFERENCES index_metadata(index_id),
    trade_date          DATE,
    open_price          DECIMAL,
    high_price          DECIMAL,
    low_price           DECIMAL,
    close_price         DECIMAL,
    shares_traded       DECIMAL,
    turnover_inr_cr      DECIMAL,
    last_updated_time   TIMESTAMP,
    PRIMARY KEY (index_id, trade_date)
);

CREATE TABLE valuation_metadata (
    index_id            INT REFERENCES index_metadata(index_id),
    trade_date          DATE,
    pe_ratio            DECIMAL,
    pb_ratio            DECIMAL,
    div_yield           DECIMAL,
    last_updated_time   TIMESTAMP,
    PRIMARY KEY (index_id, trade_date)
);

CREATE TABLE advance_decline_metadata (
    trade_date              DATE PRIMARY KEY,
    advances                DECIMAL,
    declines                DECIMAL,
    advance_decline_ratio   DECIMAL,
    last_updated_time       TIMESTAMP
);

CREATE TABLE india_vix_metadata (
    index_id                INT,
    trade_date               DATE,
    open_price               DECIMAL,
    high_price                DECIMAL,
    low_price                 DECIMAL,
    close_price               DECIMAL,
    previous_close_price     DECIMAL,
    points_change            DECIMAL,
    percentage_change        DECIMAL,
    last_updated_time        TIMESTAMP,
    PRIMARY KEY (index_id, trade_date)
);
```

> `index_metadata` needs to be seeded with the `Trading_Index_Name` (NiftyIndices) ↔ `Index_long_name` (NSE India) mapping for every index you track before the fetchers can look up an `index_id`. The current scripts define this mapping inline (see each script's hard-coded `index_dictionary`) rather than in a single shared reference file — see the [Roadmap](#roadmap-ideas) item about consolidating it.

> ⚠️ **The database host, port, and database name are hardcoded literals**, duplicated identically in every script (`daily_fetcher_price.py`, `data_ingestion_price.py`, `valuation_daily_fetcher.py`, etc.) — e.g. `f"cockroachdb://postgres:{database_password}@<cluster-host>:26257/<db-name>?sslmode=verify-full"`. Only the password is read from the environment (`database_password_cockroach_db`). This means migrating to a different CockroachDB cluster (as already happened once — see the egress-limits note below) requires a find-and-replace across every `.py` file, not a single config change. Consolidating this into one shared connection-string builder is on the [Roadmap](#roadmap-ideas).

---

## Setup

> These instructions are for deploying this exact codebase for its own use case; see [License](#license) before reusing any part of it elsewhere.

### 1. Clone & install dependencies

```bash
git clone <this-repo-url>
cd <this-repo>
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Provision a database

Any Postgres-wire-compatible database works; the scripts were built against **CockroachDB Cloud** (`sslmode=verify-full`). Create the tables from the [schema above](#database-schema-expected-tables), then seed `index_metadata` using the `index_dictionary` mapping defined in the fetcher scripts (see the note in [Database Schema](#database-schema-expected-tables)).

### 3. Configure environment variables

Create a `.env` file in the project root (see [below](#environment-variables)).

### 4. Run a script

```bash
python daily_fetcher_price.py
```

---

## Environment Variables

Create a `.env` file (never commit this — add it to `.gitignore`):

```dotenv
# CockroachDB / Postgres connection
database_password_cockroach_db=your_cockroachdb_password

# Email reporting (logs_email.py) — Gmail SMTP over SSL
sender_email=you@gmail.com
receiver_email=you@gmail.com
email_app_password=your_gmail_app_password
owner_name=your_linux_username        # used to build /home/<owner_name>/Megadox/logs/... path
```

> `email_app_password` must be a Gmail **App Password**, not your regular account password (Gmail requires 2FA + App Passwords for SMTP access from scripts).

---

## Usage

### Daily fetchers (designed for cron / CI)

Each daily fetcher fetches the previous calendar day's data (`date.today() - timedelta(days=1)`) for every index in its hard-coded `index_dictionary`, cleans it, and inserts it.

```bash
python daily_fetcher_price.py
python valuation_daily_fetcher.py
python adv_dec_daily_fetcher.py
python india_vix_daily.py
python logs_email.py   # optional: emails today's log file as an attachment
```

> ⚠️ **Only `adv_dec_daily_fetcher.py` checks the day of week and exits early on Saturday/Sunday.** `daily_fetcher_price.py`, `valuation_daily_fetcher.py`, and `india_vix_daily.py` have no such guard and will attempt to run every day — see [Known Quirks](#known-quirks--gotchas) for what actually happens when they do.

**Historical GCP VM crontab** (IST) — this is what actually ran the pipeline for the project's first ~3 months, before it moved to [GitHub Actions](#cicd-github-actions). Reconstructed from real execution logs, not illustrative:

```cron
30 16 * * *  cd /home/<user>/Megadox && git pull                                                        >> logs/fetch_log_$(date +\%d-\%m-\%Y).md 2>&1
45 16 * * *  cd /home/<user>/Megadox && /home/<user>/Megadox/venv/bin/python daily_fetcher_price.py      >> logs/fetch_log_$(date +\%d-\%m-\%Y).md 2>&1
15 17 * * *  cd /home/<user>/Megadox && /home/<user>/Megadox/venv/bin/python valuation_daily_fetcher.py  >> logs/fetch_log_$(date +\%d-\%m-\%Y).md 2>&1
45 17 * * *  cd /home/<user>/Megadox && /home/<user>/Megadox/venv/bin/python india_vix_daily.py          >> logs/fetch_log_$(date +\%d-\%m-\%Y).md 2>&1
0  18 * * *  cd /home/<user>/Megadox && /home/<user>/Megadox/venv/bin/python adv_dec_daily_fetcher.py    >> logs/fetch_log_$(date +\%d-\%m-\%Y).md 2>&1
```

Note the 30-minute spacing between steps (not 5 minutes) and the `git pull` step before every run, plus that the schedule itself has no day-of-week filter — same gap as the current GitHub Actions workflows (see [CI/CD](#cicd-github-actions)). `logs_email.py` isn't in this crontab either; the emailed log report was a separate, apparently manually-added step (see [Logging & Email Reports](#logging--email-reports)).

### Interactive historical backfills

These scripts prompt for input on the command line — run them manually, not via cron.

```bash
python data_ingestion_price.py
```
```
Enter Index ID: 3
Enter Data Source Preference (NSE INDIA/NIFTY INDICES): NSE INDIA
Enter 1 to Proceed and 0 to Abort: 1
Enter Starting Day: 1
Enter Starting Month: 1
Enter Starting Year: 2020
Enter Ending Day: 31
Enter Ending Month: 12
Enter Ending Year: 2024
```

The script then walks the date range in rolling 30-day windows (NSE India's historical endpoints reject windows wider than ~1 year, and NiftyIndices' response quality degrades noticeably beyond ~3–4 months per the notes in `Payload_Analysis.pdf`), sleeping a random 1–10 seconds between requests, and reconciles the ingested dates against the official NSE/BSE trading calendars at the end.

Same day/month-range pattern applies to:

```bash
python valuation_data_ingestion.py
python vix_historical_data_fetch.py
```

`adv_dec_ingestion.py` prompts for a **month range** instead of exact days, and pulls exclusively from NSE India's monthly advance/decline endpoint (no NiftyIndices option, no data-source prompt):

```
Enter Starting Month (First Three Letters of Month): JAN
Enter Starting Year: 2023
Enter Ending Month (First Three Letters of Month): DEC
Enter Ending Year: 2024
```

---

## CI/CD (GitHub Actions)

Two scheduled workflows in `.github/workflows/` run the daily fetchers on GitHub-hosted runners, independent of any local cron setup:

| Workflow file | Name | Scripts run (in order) |
|---|---|---|
| `price_valuation_india_vix.yml` | Daily Price, Valuation and India Vix Database Updater | `daily_fetcher_price.py` → `valuation_daily_fetcher.py` → `india_vix_daily.py` |
| `advance_decline.yml` | Daily Advance Decline Database Updater | `adv_dec_daily_fetcher.py` |

**Trigger:** both run on `schedule: cron: '30 12 * * *'` (12:30 UTC = **18:00 IST**, every day of the week) plus `workflow_dispatch` for a manual "Run workflow" button. Note the cron has no day-of-week filter, and — unlike what might be assumed — only `adv_dec_daily_fetcher.py` actually checks for and skips weekends internally. `daily_fetcher_price.py`, `valuation_daily_fetcher.py`, and `india_vix_daily.py` have no such check, so `price_valuation_india_vix.yml` will attempt (and, per observed logs, fail on) all three of those scripts every Saturday and Sunday too. See [Known Quirks](#known-quirks--gotchas).

**Runner setup:** `ubuntu-latest`, Python 3.13 (`actions/setup-python@v5`), dependencies installed via `pip install -r requirements.txt`, each script run with `PYTHONUNBUFFERED=1` (so logs stream live in the Actions UI instead of buffering).

**Secrets required:** only `DATABASE_PASSWORD_COCKROACH_DB`, injected as the `database_password_cockroach_db` environment variable for every script step. Set this under **Settings → Secrets and variables → Actions** in the GitHub repo.

**Gaps to be aware of:**
- Neither workflow calls `logs_email.py` — this used to run routinely when the project was deployed on a GCP VM; see [Logging & Email Reports](#logging--email-reports) for the migration history and what's needed to bring it back on Actions.
- The two historical-ingestion families (`data_ingestion_price.py`, `valuation_data_ingestion.py`, `vix_historical_data_fetch.py`, `adv_dec_ingestion.py`) are **not** wired into any workflow — they're interactive scripts and still need to be run manually.
- Because both workflows schedule for the exact same time (12:30 UTC) and hit the same CockroachDB instance, watch for connection-pool contention if your plan has a low concurrent-connection limit.
- GitHub-hosted runners share well-known IP ranges; if NSE's anti-bot layer starts throttling Actions runs more than a local/VPS cron job, that's a likely cause.

---

## How the Scraping Works

1. **Session bootstrap** — every fetch first does a plain `GET` to the site's homepage to collect anti-bot cookies before hitting the real API.
2. **Browser impersonation** — requests are sent via [`curl_cffi`](https://github.com/lexiforest/curl_cffi) with `impersonate="chrome1XX"`, matched to a randomly chosen realistic Chrome User-Agent string, so TLS/HTTP2 fingerprints look like a real browser rather than `python-requests`.
3. **Randomized pacing** — a `random.uniform(1, 10)` (or `2, 5` for the cookie-priming step) second sleep is inserted between requests to avoid bursty, obviously-automated traffic patterns.
4. **Cleaning pipeline** (`data_inject_*_database` functions):
   - Strip whitespace from all string fields.
   - Normalize a wide set of "empty" sentinel values (`"None"`, `"0"`, `"-"`, `"NaN"`, `"null"`, etc.) to `None`.
   - Cast numeric-looking values to `Decimal`; fall back to `str` if casting fails.
   - Parse source-specific date formats (`%d-%b-%Y`, `%d %b %Y`) into a single `date` object.
5. **Merge-safe upsert** *(price + valuation historical ingestion only)* — the script first `SELECT`s any existing row for that `(index_id, trade_date)`, counts how many of its fields are non-null, and compares that to how many fields the incoming API record has. It only performs an `INSERT`/`UPDATE` when the incoming row is at least as complete. `vix_historical_data_fetch.py` and `adv_dec_ingestion.py` skip this check and `INSERT` directly.
6. **Trading-calendar reconciliation** — after a price/valuation backfill, `pandas_market_calendars` computes the true set of NSE/BSE trading days in the requested range and diffs it against the set of dates actually written, surfacing any gaps or unexpected extra dates in the final summary.

**Failure handling is not uniform, and one mode is a real gap:**
- A non-200 HTTP response triggers a deliberate `sys.exit()` after logging the error code — this is intentional, if abrupt.
- A network-level failure (DNS, timeout, connection reset) is a **different story**: the `session.get(...)` call in every daily fetcher and the historical scripts is **not wrapped in `try`/`except`**, so `curl_cffi`'s exception propagates as an unhandled traceback and kills the script mid-loop — no partial results are logged for the indices after the one that failed. This is confirmed in production logs (see [Known Quirks](#known-quirks--gotchas)): two separate weekend runs both crashed identically on the very first index with a 10-second curl timeout.

---

## Reverse-Engineering Notes

The two PDFs in this repo document the process of finding and validating the private endpoints used above:

- **`Reverse_Engineering_API.pdf`** — step-by-step browser DevTools walkthrough of the NiftyIndices "Historical Data Reports" page, showing how each dropdown selection fires an XHR request, culminating in the `getHistoricaldatatabletoString` POST call and its full `cinfo` payload/response shape, plus the full index dropdown catalog returned by `gethistoricaltypeindexdata`.
- **`Payload_Analysis.pdf`** — a focused audit of payload validation quirks discovered by fuzzing the `cinfo.name` field (e.g., the backend does fuzzy/`LIKE`-style matching, ignores the `indexName` key entirely, requires the key to exist but tolerates an empty string, and crashes with what looks like a `KeyError` if the key is missing outright). This is why `index_metadata.trading_index_name` sometimes differs slightly from the "official" display name — a small suffix like " INDEX" was appended where needed to make the fuzzy match succeed for indices whose canonical long-form name is under-specified.

These notes exist purely to explain *why* the payload-construction code in `data_ingestion_price.py` / `valuation_data_ingestion.py` looks the way it does — they're not step-by-step instructions for bypassing any access controls, since none were found (these are unauthenticated, publicly reachable endpoints already used by the sites' own frontends).

---

## Logging & Email Reports

- All fetch/ingestion scripts use Python's `logging` module with a boxed, human-readable console format (`╔══╗` banners, `┌──┐` sections) rather than default log lines, so logs read cleanly when redirected to a file.
- `logs_email.py` looks for `/home/<owner_name>/Megadox/logs/fetch_log_<dd-mm-yyyy>.md` (today's date) and emails it as an attachment via Gmail SMTP over SSL (port 465), using an App Password. If the file isn't found, it still sends the email without an attachment rather than failing.

### History: GCP VM → GitHub Actions migration broke the email step

For roughly the first three months of this project, the daily scripts ran on a **Google Cloud Platform VM instance** via a real crontab (the same pattern shown in [Usage](#usage)), with `logs_email.py` running routinely as the last step — the `Sample_Emails/` folder holds examples of what those daily reports looked like.

When execution moved to **GitHub Actions**, `logs_email.py` was **not** carried over into either workflow (see [CI/CD](#cicd-github-actions)), so the routine email report has been silently off since the migration — Actions runs successfully, but no one gets notified either way.

**To restore it on GitHub Actions:**
1. Add four more repo secrets under **Settings → Secrets and variables → Actions**: `SENDER_EMAIL`, `RECEIVER_EMAIL`, `EMAIL_APP_PASSWORD`, and `OWNER_NAME`.
2. Add a final step to both `price_valuation_india_vix.yml` and `advance_decline.yml` (or a separate workflow that runs after both, via `workflow_run`) that runs `python -u "logs_email.py"` with those four values mapped to the matching environment variables.
3. **Check the path assumption first**: `logs_email.py` builds its log path from `/home/<owner_name>/Megadox/logs/...`, which matched the GCP VM's persistent home directory. On an `ubuntu-latest` Actions runner the equivalent path is `/home/runner/...` and the filesystem is wiped after every run, so `owner_name` will need to be set to `runner` (or the script adjusted to use a relative/`$GITHUB_WORKSPACE`-based path) for it to find the log file the fetcher steps just wrote.
4. Make sure the fetcher steps in the same job actually write to `logs/fetch_log_<dd-mm-yyyy>.md` on the runner (e.g. via `>> logs/fetch_log_$(date +\%d-\%m-\%Y).md`) before the email step runs — steps in the same job share the runner's filesystem, but only within that one job/workflow run.

---

## Known Quirks & Gotchas

- **NSE India historical endpoints** silently return `200 OK` with empty/partial data for windows that are too wide — keep backfill windows to ~30 days at a time (already handled by the rolling-window logic).
- **NiftyIndices' `getHistoricaldatatabletoString`** silently truncates full-year date ranges to ~3–4 months of actual data even when the request looks successful — see the note at the top of `Payload_Analysis.pdf`. Prefer NSE India for long backfills and use NiftyIndices mainly as a fallback for indices/date-ranges where NSE India has gaps.
- **The "weekend guard" only exists in `adv_dec_daily_fetcher.py`** — it checks `datetime.today().strftime("%A")` and exits via `sys.exit()` on Saturday/Sunday, specifically because NSE's `/api/live-analysis-advance` endpoint replays Friday's numbers on non-trading days. `daily_fetcher_price.py`, `valuation_daily_fetcher.py`, and `india_vix_daily.py` have **no equivalent check** and will attempt to run every day. In practice this isn't graceful — it's a crash: two independent weekend log files (Saturday 05-Sep-2026 and Sunday 19-Jul-2026) both show all three scripts timing out identically on the very first index (`curl_cffi.requests.exceptions.Timeout` after 10 seconds) and terminating via an unhandled exception, versus a clean, fully successful run across all 135 indices on a weekday (Thursday 20-Aug-2026). Since the network call isn't wrapped in `try`/`except`, this kills the entire day's run for that script with zero rows written — not just a skipped index.
- **Merge-safe upsert isn't universal**: `data_ingestion_price.py` and `valuation_data_ingestion.py` check the existing row's completeness before writing; `vix_historical_data_fetch.py` and `adv_dec_ingestion.py` do a plain `INSERT` with no such check and no `ON CONFLICT` clause. Re-running either of the latter two over a date range you've already ingested will likely raise a primary-key violation rather than silently updating.
- **Database connection details are hardcoded per-script**, not centrally configured — see the note in [Database Schema](#database-schema-expected-tables). Only the password comes from `.env`/secrets.
- **Redundant dependencies in `requirements.txt`**: `psycopg2`, `psycopg`, and `psycopg-binary` are all pinned, but only `psycopg2` is imported (and even that import appears unused directly — SQLAlchemy's CockroachDB dialect pulls it in as the underlying driver). Similarly, both `dotenv` and `python-dotenv` are pinned, though the code only ever imports `from dotenv import load_dotenv`, which is `python-dotenv`'s API. `exchange_calendars`, `korean-lunar-calendar`, `pyluach`, `reportlab`, and `pillow` aren't imported directly anywhere in the fetch/ingestion scripts — they come in transitively via `pandas_market_calendars`' support for many regional calendars.
- **Never commit `.env`** — it holds your database password and Gmail App Password. A `.gitignore` is already present in the repo root; confirm it excludes `.env`, `venv/`, `__pycache__/`, and `logs/` before your first push.
- **CockroachDB egress limits**: a recent commit ("Minor Improvements and DB Relocate due to Egress Limits") indicates the original CockroachDB Cloud instance hit its free-tier egress cap and the project's data source was relocated as a result. Because the connection details are hardcoded per-script (see above), that migration meant editing every file individually rather than one config value.

---

## Roadmap Ideas

- [x] ~~Add a `.gitignore`~~ — present in the repo root; just confirm it stays current as new scratch files appear
- [x] ~~Document the GitHub Actions workflow(s)~~ — see [CI/CD](#cicd-github-actions); both workflows and their trigger/secrets are now documented
- [ ] **Fix the weekend crash**, not just a scheduling nicety: add the same day-of-week check already used in `adv_dec_daily_fetcher.py` to `daily_fetcher_price.py`, `valuation_daily_fetcher.py`, and `india_vix_daily.py` — confirmed via production logs to fail every Saturday/Sunday otherwise
- [ ] Wrap the `session.get(...)` network calls in `try`/`except` with retry/backoff for transient timeouts, so one slow response doesn't crash the entire index loop with zero rows written for the rest of that run
- [ ] Extend the merge-safe upsert check (or at minimum an `ON CONFLICT DO NOTHING`) to `vix_historical_data_fetch.py` and `adv_dec_ingestion.py` so re-running them over an already-ingested range doesn't raise a primary-key violation
- [ ] Centralize the hardcoded CockroachDB host/port/database-name literal into one shared config or env var, instead of duplicating it across every script
- [ ] Restore the daily email report on GitHub Actions — add `SENDER_EMAIL`/`RECEIVER_EMAIL`/`EMAIL_APP_PASSWORD`/`OWNER_NAME` as repo secrets, add a `logs_email.py` step to both workflows, and fix its hard-coded `/home/<owner_name>/...` path assumption for the `ubuntu-latest` runner (see [Logging & Email Reports](#logging--email-reports))
- [ ] Move the hard-coded `index_dictionary` (repeated across the daily fetcher and ingestion scripts) into a single shared module or a DB-driven lookup, replacing the informal note in [Database Schema](#database-schema-expected-tables)
- [ ] Clean up `requirements.txt`: drop the unused `psycopg`/`psycopg-binary` (or drop `psycopg2` if migrating to psycopg 3) and the redundant `dotenv` package
- [ ] Add automated tests for the fetch/clean/upsert logic — there's no test suite in the repo yet
- [ ] Document the current database provider/plan in [Setup](#setup) now that the project has moved once already due to egress limits, so the next migration is a config change, not a rewrite
- [ ] Decide the fate of `price_data_source_metadata` and `valuation_data_source_metadata` — both exist in the live schema with 0 rows and no script writes to them; either wire them up to record which upstream source (NSE India vs. NiftyIndices) supplied each row, or drop them to avoid schema drift (see [Database Schema](#database-schema-expected-tables))
- [ ] Containerize (`Dockerfile` + `docker-compose.yml`) for easier deployment alongside the existing GitHub Actions workflow

---

## License

**Proprietary — All Rights Reserved. No reuse, copying, modification, or redistribution permitted.**

This repository is public **for viewing purposes only**. No license is granted, express or implied, to use, copy, modify, merge, publish, distribute, sublicense, or sell copies of this code, in whole or in part, for any purpose, commercial or non-commercial, without prior written permission from the copyright holder.

> ⚠️ A public GitHub repo with no `LICENSE` file does **not** mean "no restrictions" — under default copyright law, the absence of a license means *nobody* automatically has permission to reuse the code, but relying on that default is easy to overlook or misread. Add an explicit `LICENSE` file to the repo root with wording along these lines (adjust the year/holder) so the restriction is unambiguous to anyone who finds the repo, rather than relying on visitors already knowing the default rule:
>
> ```
> Copyright (c) <year> <your name/organization>. All Rights Reserved.
>
> This source code and associated documentation files are proprietary
> and confidential. Unauthorized copying, modification, distribution,
> or use of this software, via any medium, is strictly prohibited
> without the express prior written permission of the copyright holder.
> ```

If you ever *do* want others to be able to use this (e.g. as a portfolio piece people can fork and learn from, but not resell), consider a source-available license like a modified MIT with a non-commercial clause, or [PolyForm Noncommercial](https://polyformproject.org/licenses/noncommercial/1.0.0/) — but that's a deliberate opt-in, not the default you want here.
