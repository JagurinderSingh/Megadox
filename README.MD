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

Each data type has a **daily fetcher** (pulls just today's/yesterday's data, meant to run on a schedule) and a **historical ingestion** script (interactively backfills a custom date range in rolling 30-day windows, with automatic fallback between two data sources).

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
- **Insert-or-update merge logic**: before writing a row, the script counts how many non-null fields the incoming API record has vs. the existing DB row, and only overwrites if the incoming record is *at least as complete*. This avoids a "richer" existing row being clobbered by a sparser one.
- **Trading-calendar reconciliation**: `pandas_market_calendars` (NSE `XNSE`, BSE `XBOM`) is used to compute the expected set of trading days for a date range, then diffed against what was actually ingested, to flag gaps.
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
├── .gitignore                      # Excludes .env, venv/, __pycache__/, logs/, etc.
├── Sample_Emails/                  # Example daily log-report emails from the GCP-VM-cron era
│
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
├── index_check.py                  # Reference list mapping Trading_Index_Name <-> Index_long_name
├── nse_india_test.py               # Scratch/test file (empty)
├── tempCodeRunnerFile.py           # Editor scratch file (DB_URL snippet leftover — safe to delete)
├── third_party_verification.py     # Standalone verification script for the Investing.com API path
│
├── logs_email.py                   # Emails the day's markdown execution log as an attachment
├── requirements.txt                # Python dependencies
│
├── Reverse_Engineering_API.pdf     # Write-up: reverse-engineering the NiftyIndices private API
├── Payload_Analysis.pdf            # Write-up: NSE India vs NiftyIndices payload/header analysis
└── README.md
```

> **Note:** `index_check.py`, `nse_india_test.py`, `tempCodeRunnerFile.py`, and `third_party_verification.py` are working/scratch files kept in the repo history but aren't shown in every branch listing — check `main` for the current set before relying on this tree.

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

The scripts assume these tables already exist in CockroachDB (they do **not** create tables). Below is the schema inferred from the `INSERT`/`UPDATE` queries in the code — adjust as needed for your own setup:

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

> `index_check.py` contains a hard-coded reference list (`index_list`) mapping every known `Trading_Index_Name` (NiftyIndices) to its `Index_long_name` (NSE India) — use this to seed `index_metadata`.

---

## Setup

### 1. Clone & install dependencies

```bash
git clone <this-repo-url>
cd <this-repo>
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Provision a database

Any Postgres-wire-compatible database works; the scripts were built against **CockroachDB Cloud** (`sslmode=verify-full`). Create the tables from the [schema above](#database-schema-expected-tables), then seed `index_metadata` using the mapping in `index_check.py`.

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

# Legacy / local Postgres testing (used by tempCodeRunnerFile.py, third_party_verification.py)
database_password=your_local_postgres_password

# Email reporting (logs_email.py) — Gmail SMTP over SSL
sender_email=you@gmail.com
receiver_email=you@gmail.com
email_app_password=your_gmail_app_password
owner_name=your_linux_username        # used to build /home/<owner_name>/Megadox/logs/... path
```

> `email_app_password` must be a Gmail **App Password**, not your regular account password (Gmail requires 2FA + App Passwords for SMTP access from scripts).

---

## Usage

### Daily fetchers (designed for cron)

Each daily fetcher checks the day of week and exits early on Saturday/Sunday (NSE is closed), fetches the previous trading day's/current day's data for every index in its hard-coded `index_dictionary`, cleans it, and upserts it.

```bash
python daily_fetcher_price.py
python valuation_daily_fetcher.py
python adv_dec_daily_fetcher.py
python india_vix_daily.py
python logs_email.py   # optional: emails today's log file as an attachment
```

Example crontab (IST, after market close ~4 PM):

```cron
30 16 * * 1-5  cd /home/<user>/Megadox && /home/<user>/Megadox/venv/bin/python daily_fetcher_price.py       >> logs/fetch_log_$(date +\%d-\%m-\%Y).md 2>&1
35 16 * * 1-5  cd /home/<user>/Megadox && /home/<user>/Megadox/venv/bin/python valuation_daily_fetcher.py    >> logs/fetch_log_$(date +\%d-\%m-\%Y).md 2>&1
40 16 * * 1-5  cd /home/<user>/Megadox && /home/<user>/Megadox/venv/bin/python adv_dec_daily_fetcher.py      >> logs/fetch_log_$(date +\%d-\%m-\%Y).md 2>&1
45 16 * * 1-5  cd /home/<user>/Megadox && /home/<user>/Megadox/venv/bin/python india_vix_daily.py            >> logs/fetch_log_$(date +\%d-\%m-\%Y).md 2>&1
50 16 * * 1-5  cd /home/<user>/Megadox && /home/<user>/Megadox/venv/bin/python logs_email.py
```

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

Same pattern applies to:

```bash
python valuation_data_ingestion.py
python vix_historical_data_fetch.py
python adv_dec_ingestion.py    # prompts for month/year range instead of day-level range
```

---

## CI/CD (GitHub Actions)

Two scheduled workflows in `.github/workflows/` run the daily fetchers on GitHub-hosted runners, independent of any local cron setup:

| Workflow file | Name | Scripts run (in order) |
|---|---|---|
| `price_valuation_india_vix.yml` | Daily Price, Valuation and India Vix Database Updater | `daily_fetcher_price.py` → `valuation_daily_fetcher.py` → `india_vix_daily.py` |
| `advance_decline.yml` | Daily Advance Decline Database Updater | `adv_dec_daily_fetcher.py` |

**Trigger:** both run on `schedule: cron: '30 12 * * *'` (12:30 UTC = **18:00 IST**, every day of the week) plus `workflow_dispatch` for a manual "Run workflow" button. Note the cron has no day-of-week filter — the workflow fires on weekends too, relying on each script's own Saturday/Sunday guard (see [Known Quirks](#known-quirks--gotchas)) to no-op rather than the schedule itself skipping them.

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
5. **Merge-safe upsert** — for historical backfills, the script first `SELECT`s any existing row for that `(index_id, trade_date)`, counts how many of its fields are non-null, and compares that to how many fields the incoming API record has. It only performs an `INSERT`/`UPDATE` when the incoming row is at least as complete, so a partial/degraded API response can never silently overwrite a more complete existing row.
6. **Trading-calendar reconciliation** — after a backfill, `pandas_market_calendars` computes the true set of NSE/BSE trading days in the requested range and diffs it against the set of dates actually written, surfacing any gaps or unexpected extra dates in the final summary.

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
- **Weekend guard**: daily fetchers exit immediately on Saturday/Sunday since NSE India's "live" endpoints otherwise just replay Friday's data.
- **`tempCodeRunnerFile.py`** is an editor artifact (VS Code "Run Code" scratch file) left over from testing and contains a leftover DB URL snippet — delete it from the repo (not just `.gitignore` it) since it's already tracked in history.
- **`nse_india_test.py`** is currently empty — either fill it in with real tests or remove it before pushing.
- **Never commit `.env`** — it holds your database password and Gmail App Password. A `.gitignore` is already present in the repo root; confirm it excludes `.env`, `venv/`, `__pycache__/`, `logs/`, and `tempCodeRunnerFile.py` before your first push.
- **CockroachDB egress limits**: a recent commit ("Minor Improvements and DB Relocate due to Egress Limits") indicates the original CockroachDB Cloud instance hit its free-tier egress cap and the project's data source was relocated as a result. If you're forking this repo, budget for egress when choosing a plan/provider, and update the [Setup](#setup) section with whichever database endpoint you land on.

---

## Roadmap Ideas

- [x] ~~Add a `.gitignore`~~ — present in the repo root; just confirm it stays current as new scratch files appear
- [x] ~~Document the GitHub Actions workflow(s)~~ — see [CI/CD](#cicd-github-actions); both workflows and their trigger/secrets are now documented
- [ ] Restore the daily email report on GitHub Actions — add `SENDER_EMAIL`/`RECEIVER_EMAIL`/`EMAIL_APP_PASSWORD`/`OWNER_NAME` as repo secrets, add a `logs_email.py` step to both workflows, and fix its hard-coded `/home/<owner_name>/...` path assumption for the `ubuntu-latest` runner (see [Logging & Email Reports](#logging--email-reports))
- [ ] Add a day-of-week filter (`30 12 * * 1-5`) to both workflow crons, or accept the current design and rely solely on each script's internal weekend guard — pick one and note it here
- [ ] Move the hard-coded `index_dictionary` (repeated across 3+ files) into a single shared module or a DB-driven lookup
- [ ] Replace `print()`-based debug statements in `third_party_verification.py` with the same structured `logging` setup used elsewhere
- [ ] Add automated tests (`nse_india_test.py` is currently a stub) — even a smoke test would give the CI workflow something meaningful to run
- [ ] Add retry/backoff logic around transient NSE `5xx`/timeout errors instead of hard `sys.exit()`
- [ ] Document the current database provider/plan in [Setup](#setup) now that the project has moved once already due to egress limits, so the next migration is a config change, not a rewrite
- [ ] Containerize (`Dockerfile` + `docker-compose.yml`) for easier deployment alongside the existing GitHub Actions workflow
- [ ] Delete or fill in `nse_india_test.py` and `tempCodeRunnerFile.py` before the next public commit

---

## License

Not yet specified. Add a `LICENSE` file (e.g., MIT) before publishing publicly if you intend for others to reuse this code.
