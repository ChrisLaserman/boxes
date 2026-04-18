# Cutwater C-28 Boat Listing Monitor

Monitors BoatTrader, Boats.com, and YachtWorld for Cutwater C-28 listings
(2012–2021, ≤$175K) and emails you when new listings appear or prices drop.

## Requirements

- Python 3.10+
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords)

## Installation

```bash
cd cutwater_monitor
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## First run

```bash
python monitor.py
```

On the very first run the script will:
1. Prompt you for your Gmail address and App Password and save them to `.env`.
2. Scrape all three sites and build `listings_db.json` (the baseline).
3. Print how many listings were seeded — **no alert email is sent yet**.

Run it a second time (or wait for the daemon) to start receiving alerts.

To reconfigure credentials at any time:

```bash
python monitor.py --setup
```

## Usage

| Command | Effect |
|---|---|
| `python monitor.py` | Single scan, email alerts if anything changed |
| `python monitor.py --daemon` | Loop every 12 hours |
| `python monitor.py --daemon --interval 6` | Loop every 6 hours |
| `python monitor.py --setup` | Re-enter email credentials |

Logs are written to `monitor.log` in the same directory.

## Scoring rubric

Each alert is scored 1–10:

| Condition | Points |
|---|---|
| Price < $130,000 | +3 |
| Engine hours < 400 | +2 |
| Has both generator **and** thruster keywords | +2 |
| Located in VA, MD, NC, CT, NY, NJ, or FL | +1 |
| Price drop > 5% | +1 |
| Has "records" or "dealer maintained" keyword | +1 |

The highest-scoring alert appears in the email subject line, e.g.:

```
[Score 8/10] NEW: 2017 Cutwater C-28 – $142,000 – Greenwich, CT
```

## Scheduling with Windows Task Scheduler

1. Open **Task Scheduler** → *Create Basic Task*.
2. Name it `Cutwater Monitor`.
3. Trigger → **Daily**, then set a start time and check *Repeat task every 12 hours*.
4. Action → **Start a program**:
   - Program: full path to your venv Python, e.g.
     `C:\Users\You\cutwater_monitor\.venv\Scripts\python.exe`
   - Arguments: `monitor.py`
   - Start in: `C:\Users\You\cutwater_monitor`
5. Finish — the task will run even when you're logged out if you enable
   *Run whether user is logged on or not* and supply your Windows password.

Alternatively use the `--daemon` flag and add a single "run at startup" task
that keeps the process alive in the background.

## Notes on scraping

All three sites (BoatTrader, Boats.com, YachtWorld) are owned by Boats Group
and use Next.js server-side rendering. The scraper first tries to extract
listings from the embedded `__NEXT_DATA__` JSON blob, then falls back to
HTML card parsing if the JSON path changes. If a site returns a non-200
status (bot detection, CAPTCHA), the scraper logs a warning and skips that
source gracefully — the other sources still run.

If you find a site is consistently blocking requests, try adding a
`SCRAPER_DELAY` env var or switching to a residential proxy. Playwright/
Selenium can be dropped in as a `_fetch` override if JavaScript rendering
becomes necessary.

## File layout

```
cutwater_monitor/
├── monitor.py          # main script
├── requirements.txt
├── .env.example        # template — copy to .env and fill in
├── .env                # your credentials (git-ignored)
├── listings_db.json    # auto-created on first run
└── monitor.log         # auto-created on first run
```
